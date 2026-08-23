from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import json
import random
import threading
import time
from config import Config
import os
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app, supports_credentials=True)

client = MongoClient(Config.MONGO_URI)
db = client[Config.DATABASE_NAME]

patients_collection = db['patients']
beds_collection = db['beds']
staff_collection = db['staff']
triage_logs_collection = db['triage_logs']
ai_analyses_collection = db['ai_analyses']

# --------------- Bed cache ---------------
# In-memory cache so /api/beds doesn't hit Mongo on every call.
# Any route that mutates beds/patients/staff calls invalidate_beds_cache().
_beds_cache = {'data': None, 'ts': 0}
_beds_cache_lock = threading.Lock()
BEDS_CACHE_TTL = 15  # seconds

def invalidate_beds_cache():
    """Call this after any DB write that affects beds, patients, or staff."""
    with _beds_cache_lock:
        _beds_cache['data'] = None
        _beds_cache['ts'] = 0

def _build_beds_payload():
    """Fetch beds with enriched patient/staff info using batch lookups."""
    beds = list(beds_collection.find())
    if not beds:
        return beds

    # Serialize ObjectIds and datetimes
    for b in beds:
        b['_id'] = str(b['_id'])
        b['last_updated'] = b['last_updated'].isoformat() if b.get('last_updated') else None

    # Batch-collect all patient IDs we need to look up
    patient_ids = set()
    for b in beds:
        pid = b.get('patient_id')
        if pid:
            patient_ids.add(pid)

    # Also find admitted patients by assigned_bed (fallback link)
    admitted = list(patients_collection.find({'status': 'admitted'}))
    admitted_by_bed_num = {}
    admitted_by_id = {}
    for p in admitted:
        p['_id'] = str(p['_id'])
        p['check_in_time'] = p['check_in_time'].isoformat() if p.get('check_in_time') else None
        patient_ids.add(p['_id'])
        if p.get('assigned_bed'):
            admitted_by_bed_num[str(p['assigned_bed'])] = p
            admitted_by_id[p['_id']] = p

    # Batch fetch all patients we need
    patients_map = {}
    if patient_ids:
        oid_ids = []
        str_ids = []
        for pid in patient_ids:
            try:
                oid_ids.append(ObjectId(pid))
            except Exception:
                str_ids.append(pid)
        if oid_ids:
            for p in patients_collection.find({'_id': {'$in': oid_ids}}):
                p['_id'] = str(p['_id'])
                p['check_in_time'] = p['check_in_time'].isoformat() if p.get('check_in_time') else None
                patients_map[p['_id']] = p
        patients_map.update({p['_id']: p for p in admitted_by_id.values()})

    # Collect all staff IDs from all patients (batch lookup)
    staff_ids = set()
    for p in patients_map.values():
        for did in p.get('assigned_doctors', []):
            staff_ids.add(did)
        for nid in p.get('assigned_nurses', []):
            staff_ids.add(nid)

    staff_map = {}
    if staff_ids:
        oid_staff = []
        str_staff = []
        for sid in staff_ids:
            try:
                oid_staff.append(ObjectId(sid))
            except Exception:
                str_staff.append(sid)
        if oid_staff:
            for s in staff_collection.find({'_id': {'$in': oid_staff}}):
                staff_map[str(s['_id'])] = s.get('name', 'Unknown')
        # String IDs fallback (unlikely but safe)
        for sid in str_staff:
            s = staff_collection.find_one({'_id': sid})
            if s:
                staff_map[sid] = s.get('name', 'Unknown')

    # Build a set of admitted patient IDs for validation
    admitted_patient_ids = set(admitted_by_id.keys())
    # Map patient_id -> assigned_bed_number for validation
    admitted_bed_map = {}
    for pid, p in admitted_by_id.items():
        if p.get('assigned_bed'):
            admitted_bed_map[pid] = str(p['assigned_bed'])

    # Enrich each bed
    for b in beds:
        patient = None
        pid = b.get('patient_id')
        bed_num = str(b.get('bed_number', ''))

        # Validate: only consider the bed occupied if the patient_id points
        # to a patient who is actually admitted AND this is their assigned bed
        if pid and pid in admitted_patient_ids:
            assigned_bed = admitted_bed_map.get(pid)
            if assigned_bed and assigned_bed == bed_num:
                # This is the correct assigned bed
                patient = admitted_by_id[pid]
            elif not assigned_bed:
                # Patient is admitted but has no assigned bed yet - allow fallback matching
                patient = admitted_by_bed_num.get(bed_num)
            # else: patient is admitted to a DIFFERENT bed -> this bed is stale

        if not patient:
            # Fallback: match by bed_number -> admitted patient
            patient = admitted_by_bed_num.get(bed_num)

        # --- Clean up stale bed data ---
        # If bed claims to be occupied but no admitted patient matched,
        # clear the stale data in the DB and mark the bed available
        if b.get('status') == 'occupied' and not patient:
            try:
                beds_collection.update_one(
                    {'_id': ObjectId(b['_id'])},
                    {'$set': {
                        'patient_id': None,
                        'is_occupied': False,
                        'status': 'available',
                        'last_updated': datetime.now()
                    }}
                )
            except Exception as cleanup_err:
                print(f"[Beds] Cleanup error for bed {b['_id']}: {cleanup_err}")
            b['patient_id'] = None
            b['is_occupied'] = False
            b['status'] = 'available'

        if patient:
            doctors = [staff_map.get(d, 'Unknown') for d in patient.get('assigned_doctors', [])]
            nurses = [staff_map.get(n, 'Unknown') for n in patient.get('assigned_nurses', [])]
            b['patient_info'] = {
                '_id': patient.get('_id', ''),
                'name': patient.get('name', 'Unknown'),
                'phone': patient.get('phone', ''),
                'symptoms': patient.get('symptoms', []),
                'triage_category': patient.get('triage_category', 'unknown'),
                'status': patient.get('status', 'unknown'),
                'check_in_time': patient.get('check_in_time'),
                'doctors': doctors,
                'nurses': nurses,
            }
        else:
            b['patient_info'] = None
    return beds

def get_cached_beds():
    """Return beds payload, using cache if fresh, otherwise rebuild."""
    now = time.time()
    with _beds_cache_lock:
        if _beds_cache['data'] is not None and (now - _beds_cache['ts']) < BEDS_CACHE_TTL:
            return _beds_cache['data']
    data = _build_beds_payload()
    with _beds_cache_lock:
        _beds_cache['data'] = data
        _beds_cache['ts'] = time.time()
    return data

def init_database():
    wings_collection = db['wings']
# AI client initialization (supports NVIDIA NIM and OpenAI via the same openai SDK)
ai_client = None
AI_MODEL_NAME = ''
try:
    from openai import OpenAI
    api_key = Config.get_ai_key()
    placeholder_keys = ['your-openai-api-key-here', 'nvapi-your-nvidia-api-key-here', '']
    if api_key and api_key not in placeholder_keys:
        ai_client = OpenAI(
            api_key=api_key,
            base_url=Config.get_ai_base_url()
        )
        AI_MODEL_NAME = Config.get_ai_model()
        print(f"[AI] Client initialized: provider={Config.AI_PROVIDER}, model={AI_MODEL_NAME}, base_url={Config.get_ai_base_url()}")
    else:
        print(f"[AI] WARNING: API key not set for provider '{Config.AI_PROVIDER}'. AI features will be disabled.")
        print(f"[AI] Set NVIDIA_API_KEY in .env (get one free at https://build.nvidia.com)")
except ImportError:
    print("[AI] WARNING: openai package not installed. AI features will be disabled.")
    print("[AI] Run: pip install openai")
except Exception as e:
    print(f"[AI] WARNING: Failed to initialize AI client: {e}")
    if beds_collection.count_documents({}) == 0:
        wings = ['Emergency', 'ICU', 'General', 'Observation']
        bed_types = {'Emergency': 'emergency', 'ICU': 'icu', 'General': 'general', 'Observation': 'observation'}
        start_numbers = {'Emergency': 100, 'ICU': 200, 'General': 300, 'Observation': 400}
        
        for wing in wings:
            for i in range(10):
                bed_num = start_numbers.get(wing, 100) + i
                beds_collection.insert_one({
                    'bed_number': bed_num,
                    'type': bed_types.get(wing, 'general'),
                    'wing': wing,
                    'status': 'available',
                    'is_occupied': False,
                    'patient_id': None,
                    'last_updated': datetime.now()
                })
    
    if staff_collection.count_documents({}) == 0:
        roles = ['Doctor', 'Nurse']
        for i in range(1, 6):
            role = 'Doctor'
            staff_collection.insert_one({
                'staff_id': f'DTS{i:03d}',
                'name': f'Dr. Doctor {i}',
                'role': role,
                'status': random.choice(['available', 'busy', 'break', 'off-duty']),
                'current_patient': None,
                'shift': random.choice(['morning', 'evening', 'night'])
            })
        for i in range(1, 6):
            role = 'Nurse'
            staff_collection.insert_one({
                'staff_id': f'NRS{i:03d}',
                'name': f'Nurse {i}',
                'role': role,
                'status': random.choice(['available', 'busy', 'break', 'off-duty']),
                'current_patient': None,
                'shift': random.choice(['morning', 'evening', 'night'])
            })

triage_questions = [
    'What is your main symptom or injury?',
    'How long have you had these symptoms?',
    'Are you having any trouble breathing?'
]

def require_login():
    if not session.get('logged_in'):
        return False
    return True

def require_admin():
    return session.get('user_role') == 'Admin'

@app.route('/')
def index():
    if require_login():
        return redirect('/dashboard')
    return redirect('/login')

@app.route('/login')
def login_page():
    if session.get('logged_in'):
        return redirect('/dashboard')
    return render_template('login.html')

@app.route('/login-qr')
def login_qr_page():
    return render_template('login-qr.html')

@app.route('/dashboard')
def dashboard():
    if not require_login():
        return redirect('/login')
    return render_template('dashboard.html', user_role=session.get('user_role'))

@app.route('/patient-intake')
def patient_intake():
    return render_template('patient_intake.html', user_role=session.get('user_role'))

@app.route('/patient-kiosk')
def patient_kiosk():
    return render_template('patient_kiosk.html')

@app.route('/my-patients')
def my_patients_page():
    if not require_login():
        return redirect('/login')
    user_role = session.get('user_role')
    if user_role not in ['Doctor', 'Nurse']:
        return redirect('/dashboard')
    return render_template('my_patients.html', user_role=user_role)

@app.route('/api/my-patients')
def get_my_patients():
    if not require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session.get('user_id')
    user_role = session.get('user_role')
    
    if user_role == 'Doctor':
        query = {'assigned_doctors': user_id, 'status': {'$ne': 'discharged'}}
    elif user_role == 'Nurse':
        query = {'assigned_nurses': user_id, 'status': {'$ne': 'discharged'}}
    else:
        return jsonify([])
    
    patients = list(patients_collection.find(query).sort('check_in_time', -1))
    for p in patients:
        p['_id'] = str(p['_id'])
        p['check_in_time'] = p['check_in_time'].isoformat() if p.get('check_in_time') else None
        p['discharge_time'] = p['discharge_time'].isoformat() if p.get('discharge_time') else None
    
    return jsonify(patients)

@app.route('/staff')
def staff_page():
    if not require_login():
        return redirect('/login')
    return render_template('staff.html', user_role=session.get('user_role'))

@app.route('/settings')
def settings_page():
    if not require_login():
        return redirect('/login')
    if not require_admin():
        return redirect('/dashboard')
    return render_template('settings.html', user_role=session.get('user_role'))

@app.route('/waiting-room')
def waiting_room_page():
    if not require_login():
        return redirect('/login')
    return render_template('waiting_room.html', user_role=session.get('user_role'))

@app.route('/all-patients')
def all_patients_page():
    if not require_login():
        return redirect('/login')
    return render_template('all_patients.html', user_role=session.get('user_role'))

@app.route('/bed-qr')
def bed_qr_page():
    if not require_login():
        return redirect('/login')
    return render_template('bed_qr.html', user_role=session.get('user_role'))

@app.route('/bed-update/<bed_id>')
def bed_update(bed_id):
    bed = beds_collection.find_one({'_id': ObjectId(bed_id)})
    if not bed:
        return render_template('bed_qr.html', error='Bed not found', user_role=session.get('user_role'))
    
    if bed.get('status') == 'cleaning':
        beds_collection.update_one(
            {'_id': ObjectId(bed_id)},
            {'$set': {'status': 'available', 'last_updated': datetime.now()}}
        )
        invalidate_beds_cache()
        return render_template('bed_qr.html', success=f'Bed {bed["bed_number"]} marked as available!', bed=bed, user_role=session.get('user_role'))
    elif bed.get('status') == 'available':
        return render_template('bed_qr.html', info=f'Bed {bed["bed_number"]} is already available', bed=bed, user_role=session.get('user_role'))
    else:
        return render_template('bed_qr.html', error=f'Bed {bed["bed_number"]} is currently occupied', bed=bed, user_role=session.get('user_role'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    login_type = data.get('type')
    
    if login_type == 'staff':
        staff_id = data.get('staff_id', '').strip()
        staff = staff_collection.find_one({'staff_id': staff_id})
        if staff:
            session['logged_in'] = True
            session['user_id'] = str(staff['_id'])
            session['user_name'] = staff['name']
            session['user_role'] = staff['role']
            session['login_type'] = 'staff'
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid staff ID'})
    
    elif login_type == 'admin':
        admin_id = data.get('admin_id', '').strip()
        password = data.get('password', '')
        
        admin = db['admins'].find_one({'admin_id': admin_id, 'password': password})
        if admin:
            session['logged_in'] = True
            session['user_id'] = str(admin['_id'])
            session['user_name'] = admin['name']
            session['user_role'] = 'Admin'
            session['login_type'] = 'admin'
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid admin credentials'})
    
    return jsonify({'success': False, 'error': 'Invalid login type'})

@app.route('/api/logged-in-user')
def get_logged_in_user():
    if require_login():
        return jsonify({
            'logged_in': True,
            'name': session.get('user_name'),
            'role': session.get('user_role'),
            'login_type': session.get('login_type')
        })
    return jsonify({'logged_in': False})

@app.route('/api/admins')
def get_admins():
    if not require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    
    admins = list(db['admins'].find())
    for a in admins:
        a['_id'] = str(a['_id'])
        a.pop('password', None)
    return jsonify(admins)

@app.route('/api/admins', methods=['POST'])
def create_admin():
    if not require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    name = data.get('name', '').strip()
    admin_id = data.get('admin_id', '').strip()
    password = data.get('password', '')
    
    if not name or not admin_id or not password:
        return jsonify({'success': False, 'error': 'All fields required'})
    
    existing = db['admins'].find_one({'admin_id': admin_id})
    if existing:
        return jsonify({'success': False, 'error': 'Admin ID already exists'})
    
    result = db['admins'].insert_one({
        'name': name,
        'admin_id': admin_id,
        'password': password
    })
    
    return jsonify({'success': True, '_id': str(result.inserted_id)})

@app.route('/api/admins/<admin_id>', methods=['DELETE'])
def delete_admin(admin_id):
    if not require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    
    db['admins'].delete_one({'_id': ObjectId(admin_id)})
    return jsonify({'success': True})

@app.route('/api/all-patients')
def get_all_patients():
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    patients = list(patients_collection.find({'check_in_time': {'$gte': today_start}}).sort('check_in_time', -1))
    for p in patients:
        p['_id'] = str(p['_id'])
        p['check_in_time'] = p['check_in_time'].isoformat() if p.get('check_in_time') else None
        p['discharge_time'] = p['discharge_time'].isoformat() if p.get('discharge_time') else None
    return jsonify(patients)

@app.route('/api/wings')
def get_wings():
    wings = list(db['wings'].find())
    for w in wings:
        w['_id'] = str(w['_id'])
    return jsonify(wings)

@app.route('/api/wings', methods=['POST'])
def create_wing():
    data = request.json
    wing_name = data.get('name', '').strip()
    if not wing_name:
        return jsonify({'success': False, 'error': 'Wing name required'})
    
    existing = db['wings'].find_one({'name': wing_name})
    if existing:
        return jsonify({'success': False, 'error': 'Wing already exists'})
    
    result = db['wings'].insert_one({'name': wing_name})
    return jsonify({'success': True, '_id': str(result.inserted_id), 'name': wing_name})

@app.route('/api/wings/<wing_id>', methods=['DELETE'])
def delete_wing(wing_id):
    db['wings'].delete_one({'_id': ObjectId(wing_id)})
    return jsonify({'success': True})

@app.route('/api/configure-beds', methods=['POST'])
def configure_beds():
    data = request.json
    wing_name = data.get('wing', 'General')
    bed_type = data.get('type', 'general')
    count = int(data.get('count', 0))
    start_number = int(data.get('start_number', 100))
    
    if count <= 0:
        return jsonify({'success': False, 'error': 'Bed count must be positive'})
    
    existing_beds = list(beds_collection.find({'wing': wing_name}))
    if existing_beds:
        beds_collection.delete_many({'wing': wing_name})
    
    beds = []
    for i in range(count):
        beds.append({
            'bed_number': start_number + i,
            'type': bed_type,
            'wing': wing_name,
            'status': 'available',
            'patient_id': None,
            'last_updated': datetime.now()
        })
    
    if beds:
        beds_collection.insert_many(beds)
    
    invalidate_beds_cache()
    return jsonify({'success': True, 'beds_created': count, 'wing': wing_name})

@app.route('/api/triage-questions')
def get_triage_questions():
    return jsonify(triage_questions)

@app.route('/api/submit-triage', methods=['POST'])
def submit_triage():
    try:
        data = request.json
        symptoms = data.get('symptoms', [])
        duration = data.get('duration', '')
        breathing_trouble = data.get('breathing_trouble', 'no')
        family_history = data.get('family_history', 'no')
        substance_use = data.get('substance_use', 'no')
        sexually_active = data.get('sexually_active', 'no')
        medications = data.get('medications', '')
        
        triage_category = categorize_patient(symptoms, breathing_trouble)
    
        patient = {
            'name': data.get('name', 'Anonymous'),
            'age': data.get('age', 0),
            'gender': data.get('gender', ''),
            'phone': data.get('phone', ''),
            'symptoms': symptoms,
            'duration': duration,
            'breathing_trouble': breathing_trouble == 'yes',
            'family_history': family_history == 'yes',
            'substance_use': substance_use == 'yes',
            'sexually_active': sexually_active == 'yes',
            'medications': medications,
            'triage_category': triage_category,
            'status': 'waiting',
            'check_in_time': datetime.now(),
            'assigned_bed': None,
            'assigned_doctors': [],
            'assigned_nurses': [],
            'medication_history': [],
            'allergies': []
        }
        
        result = patients_collection.insert_one(patient)
        patient['_id'] = str(result.inserted_id)
        patient_id = str(result.inserted_id)
        
        triage_logs_collection.insert_one({
            'patient_id': patient_id,
            'category': triage_category,
            'timestamp': datetime.now(),
            'symptoms': symptoms
        })
        
        # Trigger AI analysis in background thread
        if ai_client:
            patient_doc = patients_collection.find_one({'_id': ObjectId(patient_id)})
            if patient_doc:
                thread = threading.Thread(
                    target=generate_ai_analysis_async,
                    args=(patient_id, patient_doc)
                )
                thread.daemon = True
                thread.start()
        
        invalidate_beds_cache()
        return jsonify({
            'success': True,
            'patient': patient,
            'category': triage_category,
            'patient_id': str(patient['_id']),
            'name': patient['name'],
            'queue_number': patients_collection.count_documents({'status': {'$ne': 'discharged'}}) + 1
        })
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()})

@app.route('/api/mark-arrived', methods=['POST'])
def mark_arrived():
    data = request.json
    patient_id = data.get('patient_id')
    
    if not patient_id:
        return jsonify({'success': False, 'error': 'Patient ID required'})
    
    # Count arrived patients for queue number
    arrived_count = patients_collection.count_documents({
        'arrived': True,
        'status': {'$ne': 'discharged'}
    })
    
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': {
            'arrived': True,
            'arrival_time': datetime.now(),
            'queue_number': arrived_count + 1,
            'status': 'arrived'
        }}
    )
    
    # Trigger AI analysis in background thread
    if ai_client:
        patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
        if patient:
            thread = threading.Thread(
                target=generate_ai_analysis_async,
                args=(patient_id, patient)
            )
            thread.daemon = True
            thread.start()
    
    invalidate_beds_cache()
    return jsonify({'success': True, 'queue_number': arrived_count + 1})

@app.route('/api/arrived-patients', methods=['GET'])
def get_arrived_patients():
    all_triaged = list(patients_collection.find({
        'status': {'$in': ['waiting', 'arrived']}
    }).sort('check_in_time', 1))
    
    for p in all_triaged:
        p['_id'] = str(p['_id'])
        p['arrival_time'] = p.get('arrival_time').isoformat() if p.get('arrival_time') else None
        p['check_in_time'] = p.get('check_in_time').isoformat() if p.get('check_in_time') else None
    
    return jsonify(all_triaged)

@app.route('/api/call-patient/<patient_id>', methods=['POST'])
def call_patient(patient_id):
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': {'called': True, 'called_at': datetime.now()}}
    )
    
    return jsonify({'success': True})

@app.route('/api/add-to-waiting-room', methods=['POST'])
def add_to_waiting_room():
    data = request.json
    
    name = data.get('name', 'Unknown')
    age = data.get('age', 0)
    gender = data.get('gender', '')
    phone = data.get('phone', '')
    triage_category = data.get('triage_category', 'simple')
    symptoms = data.get('symptoms', [])
    
    arrived_count = patients_collection.count_documents({
        'arrived': True,
        'status': {'$ne': 'discharged'}
    })
    
    patient = {
        'name': name,
        'age': age,
        'gender': gender,
        'phone': phone,
        'symptoms': symptoms,
        'triage_category': triage_category,
        'status': 'arrived',
        'arrived': True,
        'arrival_time': datetime.now(),
        'queue_number': arrived_count + 1,
        'called': False,
        'check_in_time': datetime.now(),
        'assigned_bed': None,
        'assigned_doctors': [],
        'assigned_nurses': [],
        'medication_history': [],
        'allergies': [],
        'duration': '',
        'breathing_trouble': False,
        'family_history': False,
        'substance_use': False,
        'sexually_active': False,
        'medications': ''
    }
    
    result = patients_collection.insert_one(patient)
    patient_id = str(result.inserted_id)
    
    # Trigger AI analysis in background thread
    if ai_client:
        patient['_id'] = result.inserted_id
        thread = threading.Thread(
            target=generate_ai_analysis_async,
            args=(patient_id, patient)
        )
        thread.daemon = True
        thread.start()
    
    invalidate_beds_cache()
    return jsonify({
        'success': True,
        'patient_id': patient_id,
        'queue_number': arrived_count + 1
    })

def _auto_assign_staff(patient_id, patient):
    """Auto-assign the least-busy doctor and up to 3 nurses to a patient.
    Returns (assigned_doctor_id_or_None, [assigned_nurse_ids]).
    Idempotent: skips assignment if the patient already has both a doctor and nurses."""
    if patient.get('assigned_doctors') and patient.get('assigned_nurses'):
        return None, []

    max_patients_per_staff = 100
    max_nurses_per_patient = 3

    # --- Doctor (pick the one with fewest active patients) ---
    available_doctors = list(staff_collection.find({
        'role': 'Doctor',
        'status': {'$ne': 'off-duty'}
    }))
    for doc in available_doctors:
        doc_str_id = str(doc['_id'])
        doc['current_count'] = patients_collection.count_documents({
            'assigned_doctors': doc_str_id,
            'status': {'$ne': 'discharged'}
        })
    available_doctors = [d for d in available_doctors if d['current_count'] < max_patients_per_staff]
    available_doctors.sort(key=lambda x: x['current_count'])

    assigned_doctor_id = None
    if not patient.get('assigned_doctors') and available_doctors:
        best_doc = available_doctors[0]
        assigned_doctor_id = str(best_doc['_id'])
        patients_collection.update_one(
            {'_id': ObjectId(patient_id)},
            {'$set': {'assigned_doctors': [assigned_doctor_id]}}
        )
        staff_collection.update_one(
            {'_id': best_doc['_id']},
            {'$set': {'status': 'busy'}}
        )

    # --- Nurses (fill up to max_nurses_per_patient with least-busy nurses) ---
    available_nurses = list(staff_collection.find({
        'role': 'Nurse',
        'status': {'$ne': 'off-duty'}
    }))
    for nurse in available_nurses:
        nurse_str_id = str(nurse['_id'])
        nurse['current_count'] = patients_collection.count_documents({
            'assigned_nurses': nurse_str_id,
            'status': {'$ne': 'discharged'}
        })
    available_nurses = [n for n in available_nurses if n['current_count'] < max_patients_per_staff]
    available_nurses.sort(key=lambda x: x['current_count'])

    current_nurses = len(patient.get('assigned_nurses', []))
    nurses_to_assign = min(max_nurses_per_patient - current_nurses, len(available_nurses))

    assigned_nurse_ids = []
    for i in range(nurses_to_assign):
        nurse = available_nurses[i]
        nurse_id = str(nurse['_id'])
        patients_collection.update_one(
            {'_id': ObjectId(patient_id)},
            {'$push': {'assigned_nurses': nurse_id}}
        )
        assigned_nurse_ids.append(nurse_id)
        if current_nurses + i + 1 >= 1:
            staff_collection.update_one(
                {'_id': nurse['_id']},
                {'$set': {'status': 'busy'}}
            )

    return assigned_doctor_id, assigned_nurse_ids


@app.route('/api/auto-assign/<patient_id>', methods=['POST'])
def auto_assign(patient_id):
    patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
    if not patient:
        return jsonify({'success': False, 'error': 'Patient not found'})
    
    assigned_doctor_id, assigned_nurse_ids = _auto_assign_staff(patient_id, patient)
    
    triage_category = patient.get('triage_category', 'simple')
    wing_priority = {
        'critical': ['ICU', 'Emergency'],
        'emergency': ['Emergency', 'ICU', 'General'],
        'attention': ['General', 'Observation'],
        'simple': ['Observation', 'General']
    }
    
    preferred_wings = wing_priority.get(triage_category, ['General'])
    assigned_bed = None
    
    for wing in preferred_wings:
        available_bed = beds_collection.find_one({
            'wing': wing,
            'status': 'available'
        })
        if available_bed:
            assigned_bed = available_bed
            break
    
    if not assigned_bed:
        assigned_bed = beds_collection.find_one({'status': 'available'})
    
    bed_assigned = None
    if assigned_bed:
        bed_number = assigned_bed['bed_number']
        beds_collection.update_one(
            {'bed_number': bed_number},
            {'$set': {'status': 'occupied', 'patient_id': patient_id, 'last_updated': datetime.now()}}
        )
        patients_collection.update_one(
            {'_id': ObjectId(patient_id)},
            {'$set': {'assigned_bed': bed_number, 'status': 'admitted'}}
        )
        bed_assigned = bed_number
    
    invalidate_beds_cache()
    return jsonify({
        'success': True,
        'assigned_doctor': assigned_doctor_id,
        'assigned_nurses': assigned_nurse_ids,
        'assigned_bed': bed_assigned
    })

def categorize_patient(symptoms, breathing_trouble):
    symptoms_lower = ' '.join(symptoms).lower() if isinstance(symptoms, list) else symptoms.lower()
    
    critical_keywords = ['chest pain', 'severe bleeding', 'unconscious', 'seizure', 'stroke', 'heart attack']
    emergency_keywords = ['fracture', 'deep cut', 'high fever', 'severe headache', 'severe pain']
    attention_keywords = ['cough', 'mild fever', 'nausea', 'vomiting', ' dizziness']
    
    if breathing_trouble == 'yes' or any(kw in symptoms_lower for kw in critical_keywords):
        return 'critical'
    elif any(kw in symptoms_lower for kw in emergency_keywords):
        return 'emergency'
    elif any(kw in symptoms_lower for kw in attention_keywords):
        return 'attention'
    else:
        return 'simple'


def calculate_triage_category(patient_data):
    """Calculate triage category from a patient dict (used by update_patient)."""
    symptoms = patient_data.get('symptoms', [])
    breathing = patient_data.get('breathing_trouble', False)
    # Normalize breathing_trouble: could be bool or string
    if isinstance(breathing, bool):
        breathing = 'yes' if breathing else 'no'
    return categorize_patient(symptoms, breathing)

@app.route('/api/patients')
def get_patients():
    patients = list(patients_collection.find({'status': {'$ne': 'discharged'}}).sort('check_in_time', -1))
    for p in patients:
        p['_id'] = str(p['_id'])
        p['check_in_time'] = p['check_in_time'].isoformat() if p.get('check_in_time') else None
    return jsonify(patients)

@app.route('/api/patients/<patient_id>', methods=['PUT'])
def update_patient(patient_id):
    """Update patient information, status, and symptoms.
    Doctors can change name, age, gender, phone, symptoms, status, triage_category."""
    try:
        patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid patient ID'}), 400
    if not patient:
        return jsonify({'success': False, 'error': 'Patient not found'}), 404

    data = request.json
    allowed_fields = [
        'name', 'age', 'gender', 'phone', 'symptoms', 'duration',
        'breathing_trouble', 'family_history', 'substance_use', 'sexually_active',
        'medications', 'triage_category', 'status', 'notes'
    ]

    update_fields = {}
    for field in allowed_fields:
        if field in data:
            update_fields[field] = data[field]

    if not update_fields:
        return jsonify({'success': False, 'error': 'No valid fields to update'}), 400

    # Handle status change
    new_status = update_fields.get('status')
    old_status = patient.get('status')

    if new_status and new_status != old_status:
        update_fields['status'] = new_status

        # If changing TO admitted, try to assign a bed if not already assigned
        if new_status == 'admitted' and not patient.get('assigned_bed'):
            available_bed = beds_collection.find_one({'status': 'available'})
            if available_bed:
                beds_collection.update_one(
                    {'_id': available_bed['_id']},
                    {'$set': {
                        'status': 'occupied',
                        'is_occupied': True,
                        'patient_id': patient_id,
                        'last_updated': datetime.now()
                    }}
                )
                update_fields['assigned_bed'] = available_bed['bed_number']

        # If changing AWAY from admitted, free the bed
        if old_status == 'admitted' and new_status != 'admitted' and patient.get('assigned_bed'):
            beds_collection.update_many(
                {'patient_id': patient_id},
                {'$set': {
                    'status': 'available',
                    'is_occupied': False,
                    'patient_id': None,
                    'last_updated': datetime.now()
                }}
            )
            update_fields['assigned_bed'] = None

            # Free assigned staff if discharging
            if new_status == 'discharged':
                for doc_id in patient.get('assigned_doctors', []):
                    try:
                        staff_collection.update_one(
                            {'_id': ObjectId(doc_id)},
                            {'$set': {'status': 'available', 'current_patient': None}}
                        )
                    except Exception:
                        pass
                for nurse_id in patient.get('assigned_nurses', []):
                    try:
                        staff_collection.update_one(
                            {'_id': ObjectId(nurse_id)},
                            {'$set': {'status': 'available', 'current_patient': None}}
                        )
                    except Exception:
                        pass
                update_fields['discharge_time'] = datetime.now().isoformat()
                update_fields['assigned_doctors'] = []
                update_fields['assigned_nurses'] = []

    # Recalculate triage if symptoms or related fields changed
    triage_fields = {'symptoms', 'duration', 'breathing_trouble', 'family_history',
                     'substance_use', 'sexually_active'}
    if triage_fields.intersection(set(update_fields.keys())):
        # Merge current patient data with updates for recalculation
        merged = dict(patient)
        merged.update(update_fields)
        new_category = calculate_triage_category(merged)
        if new_category and new_category != patient.get('triage_category'):
            update_fields['triage_category'] = new_category

    # If triage_category was explicitly set, use that
    if 'triage_category' in data and data['triage_category'] in ['simple', 'attention', 'emergency', 'critical']:
        update_fields['triage_category'] = data['triage_category']

    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': update_fields}
    )

    invalidate_beds_cache()
    return jsonify({'success': True, 'updated_fields': list(update_fields.keys())})


@app.route('/api/patients/<patient_id>', methods=['GET'])
def get_single_patient(patient_id):
    """Get a single patient by ID."""
    try:
        patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid patient ID'}), 400
    if not patient:
        return jsonify({'success': False, 'error': 'Patient not found'}), 404
    patient['_id'] = str(patient['_id'])
    patient['check_in_time'] = patient['check_in_time'].isoformat() if patient.get('check_in_time') else None
    if patient.get('discharge_time') and isinstance(patient['discharge_time'], datetime):
        patient['discharge_time'] = patient['discharge_time'].isoformat()
    return jsonify(patient)

@app.route('/api/beds')
def get_beds():
    return jsonify(get_cached_beds())

@app.route('/api/beds/<bed_id>', methods=['PUT'])
def update_bed(bed_id):
    data = request.json
    data['last_updated'] = datetime.now()
    beds_collection.update_one(
        {'_id': ObjectId(bed_id)},
        {'$set': data}
    )
    invalidate_beds_cache()
    return jsonify({'success': True})

@app.route('/api/beds/<bed_id>', methods=['DELETE'])
def delete_bed(bed_id):
    beds_collection.delete_one({'_id': ObjectId(bed_id)})
    invalidate_beds_cache()
    return jsonify({'success': True})

@app.route('/api/beds-by-wing/<wing_name>', methods=['DELETE'])
def delete_beds_by_wing(wing_name):
    result = beds_collection.delete_many({'wing': wing_name})
    invalidate_beds_cache()
    return jsonify({'success': True, 'deleted_count': result.deleted_count})

@app.route('/api/staff')
def get_staff():
    staff = list(staff_collection.find())
    for s in staff:
        s['_id'] = str(s['_id'])
        if s['role'] == 'Doctor':
            s['patient_count'] = patients_collection.count_documents({
                'assigned_doctors': s['_id'],
                'status': {'$ne': 'discharged'}
            })
        else:
            s['patient_count'] = patients_collection.count_documents({
                'assigned_nurses': s['_id'],
                'status': {'$ne': 'discharged'}
            })
    return jsonify(staff)

@app.route('/api/staff/<staff_id>', methods=['PUT'])
def update_staff(staff_id):
    data = request.json
    staff_collection.update_one(
        {'_id': ObjectId(staff_id)},
        {'$set': data}
    )
    invalidate_beds_cache()
    return jsonify({'success': True})

@app.route('/api/staff', methods=['POST'])
def create_staff():
    data = request.json
    name = data.get('name', '').strip()
    role = data.get('role', 'Nurse')
    shift = data.get('shift', 'morning')
    status = data.get('status', 'available')
    
    if not name:
        return jsonify({'success': False, 'error': 'Staff name required'})
    
    if role not in ['Doctor', 'Nurse']:
        return jsonify({'success': False, 'error': 'Invalid role'})
    
    if role == 'Doctor':
        doctor_count = staff_collection.count_documents({'role': 'Doctor'})
        staff_id = f'DTS{doctor_count + 1:03d}'
    else:
        nurse_count = staff_collection.count_documents({'role': 'Nurse'})
        staff_id = f'NRS{nurse_count + 1:03d}'
    
    result = staff_collection.insert_one({
        'staff_id': staff_id,
        'name': name,
        'role': role,
        'shift': shift,
        'status': status,
        'current_patient': None
    })
    
    invalidate_beds_cache()
    return jsonify({'success': True, '_id': str(result.inserted_id), 'staff_id': staff_id})

@app.route('/api/staff/<staff_id>', methods=['DELETE'])
def delete_staff(staff_id):
    staff_collection.delete_one({'_id': ObjectId(staff_id)})
    invalidate_beds_cache()
    return jsonify({'success': True})

@app.route('/api/assign-bed', methods=['POST'])
def assign_bed():
    data = request.json
    patient_id = data.get('patient_id')
    bed_id = data.get('bed_id')
    
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': {'assigned_bed': bed_id, 'status': 'admitted'}}
    )
    
    beds_collection.update_one(
        {'_id': ObjectId(bed_id)},
        {'$set': {'status': 'occupied', 'patient_id': patient_id, 'last_updated': datetime.now()}}
    )
    
    # Auto-assign a doctor and nurses when a patient gets a bed
    patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
    assigned_doctor_id, assigned_nurse_ids = _auto_assign_staff(patient_id, patient)
    
    invalidate_beds_cache()
    return jsonify({
        'success': True,
        'assigned_doctor': assigned_doctor_id,
        'assigned_nurses': assigned_nurse_ids
    })

@app.route('/api/assign-staff', methods=['POST'])
def assign_staff():
    data = request.json
    patient_id = data.get('patient_id')
    staff_id = data.get('staff_id')
    
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': {'assigned_staff': staff_id}}
    )
    
    staff_collection.update_one(
        {'_id': ObjectId(staff_id)},
        {'$set': {'status': 'busy', 'current_patient': patient_id}}
    )
    
    invalidate_beds_cache()
    return jsonify({'success': True})

@app.route('/api/discharge', methods=['POST'])
def discharge_patient():
    data = request.json
    patient_id = data.get('patient_id')
    
    patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
    if patient and patient.get('assigned_bed'):
        beds_collection.update_one(
            {'bed_number': patient['assigned_bed']},
            {'$set': {'status': 'cleaning', 'patient_id': None, 'last_updated': datetime.now()}}
        )
    
    if patient and patient.get('assigned_doctors'):
        for doc_id in patient['assigned_doctors']:
            remaining_patients = patients_collection.count_documents({
                'assigned_doctors': doc_id,
                'status': {'$ne': 'discharged'},
                '_id': {'$ne': ObjectId(patient_id)}
            })
            new_status = 'available' if remaining_patients == 0 else 'busy'
            staff_collection.update_one(
                {'_id': ObjectId(doc_id)},
                {'$set': {'status': new_status}}
            )
    
    if patient and patient.get('assigned_nurses'):
        for nurse_id in patient['assigned_nurses']:
            remaining_patients = patients_collection.count_documents({
                'assigned_nurses': nurse_id,
                'status': {'$ne': 'discharged'},
                '_id': {'$ne': ObjectId(patient_id)}
            })
            new_status = 'available' if remaining_patients == 0 else 'busy'
            staff_collection.update_one(
                {'_id': ObjectId(nurse_id)},
                {'$set': {'status': new_status}}
            )
    
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': {'status': 'discharged', 'discharge_time': datetime.now()}}
    )
    
    invalidate_beds_cache()
    return jsonify({'success': True})

def generate_ai_analysis(patient):
    """Generate AI-powered clinical analysis for a patient."""
    if not ai_client:
        return None
    
    patient_data = {
        'name': patient.get('name', 'Anonymous'),
        'age': patient.get('age', 'Unknown'),
        'gender': patient.get('gender', 'Unknown'),
        'symptoms': patient.get('symptoms', []),
        'duration': patient.get('duration', 'Unknown'),
        'breathing_trouble': patient.get('breathing_trouble', False),
        'family_history': patient.get('family_history', False),
        'substance_use': patient.get('substance_use', False),
        'sexually_active': patient.get('sexually_active', False),
        'medications': patient.get('medications', ''),
        'current_triage_category': patient.get('triage_category', 'unknown')
    }
    
    system_prompt = """You are an expert AI medical triage assistant embedded in a hospital management system called TriageFlow. 
Your role is to analyze patient intake data and provide clinical insights to help medical staff make informed decisions.
IMPORTANT: You are NOT providing medical diagnoses to patients. You are assisting medical professionals with clinical decision support.
Respond ONLY with valid JSON (no markdown, no code blocks). Use this exact structure:
{
    "recommended_category": "simple|attention|emergency|critical",
    "confidence": "high|medium|low",
    "reasoning": "Brief explanation of why this triage category is recommended (2-3 sentences)",
    "possible_conditions": [
        {"name": "Condition name", "likelihood": "high|medium|low", "notes": "Brief note"}
    ],
    "suggested_tests": [
        {"name": "Test name", "priority": "urgent|routine", "reason": "Why this test"}
    ],
    "risk_factors": ["Risk factor 1", "Risk factor 2"],
    "clinical_summary": "A concise 3-4 sentence clinical summary for the attending physician",
    "immediate_actions": ["Action 1", "Action 2"],
    "patient_instructions": "Clear instructions to give the patient based on their condition",
    "red_flags": ["Any warning signs to watch for"]
}
Be thorough but concise. Base your analysis on the provided patient data. Consider age, gender, and all symptoms together.
For possible_conditions, list at most 5 conditions ranked by likelihood. For suggested_tests, list at most 5 tests.
Always prioritize patient safety - when in doubt, recommend a higher triage category."""

    user_prompt = f"""Analyze this patient intake data and provide a comprehensive clinical assessment:

Patient: {patient_data['name']}, Age: {patient_data['age']}, Gender: {patient_data['gender']}
Symptoms: {', '.join(patient_data['symptoms']) if patient_data['symptoms'] else 'None specified'}
Duration: {patient_data['duration']}
Breathing difficulty: {'Yes' if patient_data['breathing_trouble'] else 'No'}
Family history: {'Yes' if patient_data['family_history'] else 'No'}
Substance use: {'Yes' if patient_data['substance_use'] else 'No'}
Sexually active: {'Yes' if patient_data['sexually_active'] else 'No'}
Medications: {patient_data['medications'] if patient_data['medications'] else 'None reported'}
Current rule-based triage: {patient_data['current_triage_category']}"""

    try:
        # Try with response_format first (supported by OpenAI and some NVIDIA NIM models)
        try:
            response = ai_client.chat.completions.create(
                model=AI_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
        except Exception as fmt_err:
            # Fallback: retry without response_format (some NVIDIA NIM models don't support it)
            print(f"[AI] response_format not supported, retrying without it: {fmt_err}")
            response = ai_client.chat.completions.create(
                model=AI_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
        content = response.choices[0].message.content
        # Strip markdown code fences if the model wraps JSON in ```json ... ```
        content = content.strip()
        if content.startswith('```'):
            lines = content.split('\n')
            lines = [l for l in lines if not l.strip().startswith('```')]
            content = '\n'.join(lines)
        analysis = json.loads(content)
        analysis['generated_at'] = datetime.now().isoformat()
        analysis['model_used'] = AI_MODEL_NAME
        analysis['status'] = 'completed'
        return analysis
    except Exception as e:
        print(f"[AI] Error generating analysis: {e}")
        return {'status': 'error', 'error': str(e), 'generated_at': datetime.now().isoformat()}


def generate_ai_analysis_async(patient_id, patient):
    """Generate AI analysis in background thread and store in database."""
    try:
        analysis = generate_ai_analysis(patient)
        if analysis:
            ai_analyses_collection.update_one(
                {'patient_id': patient_id},
                {'$set': {'patient_id': patient_id, 'analysis': analysis, 'updated_at': datetime.now()}},
                upsert=True
            )
            print(f"[AI] Analysis stored for patient {patient_id}")
    except Exception as e:
        print(f"[AI] Background analysis error for {patient_id}: {e}")


@app.route('/api/ai-analysis/<patient_id>', methods=['GET'])
def get_ai_analysis(patient_id):
    """Retrieve existing AI analysis for a patient."""
    analysis_doc = ai_analyses_collection.find_one({'patient_id': patient_id})
    if not analysis_doc:
        return jsonify({'status': 'not_found', 'analysis': None})
    return jsonify({
        'status': 'found',
        'analysis': analysis_doc.get('analysis'),
        'updated_at': analysis_doc.get('updated_at').isoformat() if analysis_doc.get('updated_at') else None
    })


@app.route('/api/ai-analysis/<patient_id>/generate', methods=['POST'])
def trigger_ai_analysis(patient_id):
    """Trigger AI analysis generation for a patient (synchronous)."""
    if not ai_client:
        return jsonify({'success': False, 'error': 'AI features are not configured. Please set your API key in the .env file.'}), 503
    patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
    if not patient:
        return jsonify({'success': False, 'error': 'Patient not found'}), 404
    analysis = generate_ai_analysis(patient)
    if analysis and analysis.get('status') != 'error':
        ai_analyses_collection.update_one(
            {'patient_id': patient_id},
            {'$set': {'patient_id': patient_id, 'analysis': analysis, 'updated_at': datetime.now()}},
            upsert=True
        )
        return jsonify({'success': True, 'analysis': analysis})
    else:
        error_msg = analysis.get('error', 'Unknown error') if analysis else 'AI service unavailable'
        return jsonify({'success': False, 'error': error_msg}), 500


@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    """Chat with AI about a specific patient or general medical questions."""
    if not ai_client:
        return jsonify({'success': False, 'error': 'AI features are not configured. Please set your API key in the .env file.'}), 503
    data = request.json
    message = data.get('message', '')
    patient_id = data.get('patient_id')
    conversation_history = data.get('history', [])
    if not message.strip():
        return jsonify({'success': False, 'error': 'Message is required'}), 400

    system_prompt = """You are TriageFlow AI, an expert medical assistant in a hospital triage system.
You help medical staff with clinical questions and patient assessments.
Guidelines:
- Be concise and clinically relevant
- Remind staff your suggestions are decision-support, not replacements for clinical judgment
- Use medical terminology since your audience is medical professionals
- Prioritize patient safety in all recommendations
- Keep responses focused and actionable"""

    messages = [{"role": "system", "content": system_prompt}]
    if patient_id:
        try:
            patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
            if patient:
                ctx = f"Patient: {patient.get('name','?')}, Age: {patient.get('age','?')}, Gender: {patient.get('gender','?')}, Symptoms: {', '.join(patient.get('symptoms',[]))}, Duration: {patient.get('duration','?')}, Breathing: {patient.get('breathing_trouble',False)}, Triage: {patient.get('triage_category','?')}, Meds: {patient.get('medications','None')}"
                messages.append({"role": "system", "content": f"Patient Context: {ctx}"})
        except Exception:
            pass
    for entry in conversation_history[-10:]:
        messages.append({"role": entry.get('role', 'user'), "content": entry.get('content', '')})
    messages.append({"role": "user", "content": message})
    try:
        response = ai_client.chat.completions.create(
            model=AI_MODEL_NAME, messages=messages, temperature=0.4, max_tokens=1000
        )
        return jsonify({'success': True, 'reply': response.choices[0].message.content, 'model': AI_MODEL_NAME})
    except Exception as e:
        print(f"[AI] Chat error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai-status')
def ai_status():
    """Check if AI features are available."""
    return jsonify({
        'enabled': ai_client is not None,
        'provider': Config.AI_PROVIDER,
        'model': AI_MODEL_NAME if ai_client else None
    })


@app.route('/api/stats')
def get_stats():
    total_patients = patients_collection.count_documents({})
    waiting = patients_collection.count_documents({'status': 'waiting'})
    admitted = patients_collection.count_documents({'status': 'admitted'})
    discharged = patients_collection.count_documents({'status': 'discharged'})

    available_beds = beds_collection.count_documents({'status': 'available'})
    occupied_beds = beds_collection.count_documents({'status': 'occupied'})
    cleaning_beds = beds_collection.count_documents({'status': 'cleaning'})

    available_staff = staff_collection.count_documents({'status': 'available'})
    busy_staff = staff_collection.count_documents({'status': 'busy'})

    return jsonify({
        'patients': {
            'total': total_patients,
            'waiting': waiting,
            'admitted': admitted,
            'discharged': discharged
        },
        'beds': {
            'available': available_beds,
            'occupied': occupied_beds,
            'cleaning': cleaning_beds,
            'total': available_beds + occupied_beds + cleaning_beds
        },
        'staff': {
            'available': available_staff,
            'busy': busy_staff,
            'total': available_staff + busy_staff
        }
    })

if __name__ == '__main__':
    init_database()
    app.run(debug=True, port=5000)