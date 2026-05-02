from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import json
import random
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

def init_database():
    wings_collection = db['wings']
    if wings_collection.count_documents({}) == 0:
        default_wings = ['Emergency', 'ICU', 'General', 'Observation', 'Pediatrics', 'Surgery']
        for wing_name in default_wings:
            wings_collection.insert_one({'name': wing_name})
    
    admins_collection = db['admins']
    if admins_collection.count_documents({}) == 0:
        admins_collection.insert_one({
            'admin_id': 'ADMIN001',
            'name': 'Hospital Admin',
            'password': 'admin123'
        })
    
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
                    'status': random.choice(['available', 'occupied', 'cleaning']),
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

@app.route('/condition-x')
def condition_x():
    if not require_login():
        return redirect('/login')
    return render_template('condition_x.html', user_role=session.get('user_role'))

@app.route('/settings')
def settings_page():
    if not require_login():
        return redirect('/login')
    if not require_admin():
        return redirect('/dashboard')
    return render_template('settings.html', user_role=session.get('user_role'))

@app.route('/all-patients')
def all_patients_page():
    if not require_login():
        return redirect('/login')
    return render_template('all_patients.html', user_role=session.get('user_role'))

@app.route('/waiting-room')
def waiting_room_page():
    if not require_login():
        return redirect('/login')
    return render_template('waiting_room.html', user_role=session.get('user_role'))

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
    
    return jsonify({'success': True, 'beds_created': count, 'wing': wing_name})

@app.route('/api/triage-questions')
def get_triage_questions():
    return jsonify(triage_questions)

@app.route('/api/submit-triage', methods=['POST'])
def submit_triage():
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
    
    triage_logs_collection.insert_one({
        'patient_id': str(result.inserted_id),
        'category': triage_category,
        'timestamp': datetime.now(),
        'symptoms': symptoms
    })
    
    return jsonify({
        'success': True,
        'patient': patient,
        'category': triage_category,
        'patient_id': str(patient['_id']),
        'name': patient['name'],
        'queue_number': patients_collection.count_documents({'status': {'$ne': 'discharged'}}) + 1
    })

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
    
    return jsonify({'success': True, 'queue_number': arrived_count + 1})

@app.route('/api/arrived-patients', methods=['GET'])
def get_arrived_patients():
    arrived = list(patients_collection.find({
        'arrived': True,
        'status': {'$ne': 'discharged'}
    }).sort('queue_number', 1))
    
    for p in arrived:
        p['_id'] = str(p['_id'])
        p['arrival_time'] = p.get('arrival_time').isoformat() if p.get('arrival_time') else None
        p['check_in_time'] = p.get('check_in_time').isoformat() if p.get('check_in_time') else None
    
    return jsonify(arrived)

@app.route('/api/call-patient/<patient_id>', methods=['POST'])
def call_patient():
    data = request.json
    patient_id = data.get('patient_id')
    
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': {'called': True, 'called_at': datetime.now()}}
    )
    
    return jsonify({'success': True})

@app.route('/api/auto-assign/<patient_id>', methods=['POST'])
def auto_assign(patient_id):
    patient = patients_collection.find_one({'_id': ObjectId(patient_id)})
    if not patient:
        return jsonify({'success': False, 'error': 'Patient not found'})
    
    if patient.get('assigned_doctors') and patient.get('assigned_nurses'):
        return jsonify({'success': True, 'message': 'Already assigned'})
    
    max_patients_per_staff = 100
    max_nurses_per_patient = 3
    
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
    
    assigned_doctor = None
    if available_doctors:
        assigned_doctor = available_doctors[0]
        patients_collection.update_one(
            {'_id': ObjectId(patient_id)},
            {'$set': {'assigned_doctors': [str(assigned_doctor['_id'])]}}
        )
        staff_collection.update_one(
            {'_id': assigned_doctor['_id']},
            {'$set': {'status': 'busy'}}
        )
    
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
    
    assigned_nurses = []
    for i in range(nurses_to_assign):
        nurse = available_nurses[i]
        patients_collection.update_one(
            {'_id': ObjectId(patient_id)},
            {'$push': {'assigned_nurses': str(nurse['_id'])}}
        )
        assigned_nurses.append(str(nurse['_id']))
        if current_nurses + i + 1 >= 1:
            staff_collection.update_one(
                {'_id': nurse['_id']},
                {'$set': {'status': 'busy'}}
            )
    
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
    
    return jsonify({
        'success': True,
        'assigned_doctor': str(assigned_doctor['_id']) if assigned_doctor else None,
        'assigned_nurses': assigned_nurses,
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

@app.route('/api/patients')
def get_patients():
    patients = list(patients_collection.find({'status': {'$ne': 'discharged'}}).sort('check_in_time', -1))
    for p in patients:
        p['_id'] = str(p['_id'])
        p['check_in_time'] = p['check_in_time'].isoformat() if p.get('check_in_time') else None
    return jsonify(patients)

@app.route('/api/patients/<patient_id>', methods=['PUT'])
def update_patient(patient_id):
    data = request.json
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': data}
    )
    return jsonify({'success': True})

@app.route('/api/beds')
def get_beds():
    beds = list(beds_collection.find())
    for b in beds:
        b['_id'] = str(b['_id'])
        b['last_updated'] = b['last_updated'].isoformat() if b.get('last_updated') else None
        
        patient = None
        if b.get('patient_id'):
            try:
                patient = patients_collection.find_one({'_id': ObjectId(b['patient_id'])})
            except:
                patient = patients_collection.find_one({'_id': b['patient_id']})
        
        if not patient and b.get('bed_number'):
            patient = patients_collection.find_one({'assigned_bed': b['bed_number'], 'status': 'admitted'})
            if not patient:
                patient = patients_collection.find_one({'assigned_bed': str(b['_id']), 'status': 'admitted'})
        
        if patient:
            b['patient_info'] = {
                'name': patient.get('name', 'Unknown'),
                'phone': patient.get('phone', ''),
                'symptoms': patient.get('symptoms', []),
                'triage_category': patient.get('triage_category', 'unknown'),
                'status': patient.get('status', 'unknown'),
                'check_in_time': patient.get('check_in_time').isoformat() if patient.get('check_in_time') else None
            }
            doctors = []
            nurses = []
            for doc_id in patient.get('assigned_doctors', []):
                try:
                    doc = staff_collection.find_one({'_id': ObjectId(doc_id)})
                except:
                    doc = staff_collection.find_one({'_id': doc_id})
                if doc:
                    doctors.append(doc.get('name', 'Unknown'))
            for nurse_id in patient.get('assigned_nurses', []):
                try:
                    nurse = staff_collection.find_one({'_id': ObjectId(nurse_id)})
                except:
                    nurse = staff_collection.find_one({'_id': nurse_id})
                if nurse:
                    nurses.append(nurse.get('name', 'Unknown'))
            b['patient_info']['doctors'] = doctors
            b['patient_info']['nurses'] = nurses
    return jsonify(beds)

@app.route('/api/beds/<bed_id>', methods=['PUT'])
def update_bed(bed_id):
    data = request.json
    data['last_updated'] = datetime.now()
    beds_collection.update_one(
        {'_id': ObjectId(bed_id)},
        {'$set': data}
    )
    return jsonify({'success': True})

@app.route('/api/beds/<bed_id>', methods=['DELETE'])
def delete_bed(bed_id):
    beds_collection.delete_one({'_id': ObjectId(bed_id)})
    return jsonify({'success': True})

@app.route('/api/beds-by-wing/<wing_name>', methods=['DELETE'])
def delete_beds_by_wing(wing_name):
    result = beds_collection.delete_many({'wing': wing_name})
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
    
    return jsonify({'success': True, '_id': str(result.inserted_id), 'staff_id': staff_id})

@app.route('/api/staff/<staff_id>', methods=['DELETE'])
def delete_staff(staff_id):
    staff_collection.delete_one({'_id': ObjectId(staff_id)})
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
    
    return jsonify({'success': True})

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
    
    return jsonify({'success': True})

@app.route('/api/condition-x-status')
def condition_x_status():
    one_hour_ago = datetime.now() - timedelta(hours=1)
    recent_logs = list(triage_logs_collection.find({'timestamp': {'$gte': one_hour_ago}}))
    
    breathing_count = sum(1 for log in recent_logs if log.get('symptoms') and 'breathing' in ' '.join(log['symptoms']).lower())
    total_triages = len(recent_logs)
    
    spike_detected = breathing_count >= 3 and total_triages >= 5
    
    category_counts = {'simple': 0, 'attention': 0, 'emergency': 0, 'critical': 0}
    for log in recent_logs:
        cat = log.get('category', 'simple')
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    return jsonify({
        'spike_detected': spike_detected,
        'breathing_symptoms_count': breathing_count,
        'total_triages_last_hour': total_triages,
        'category_counts': category_counts,
        'alert_level': 'critical' if spike_detected else 'normal',
        'recommended_actions': [
            'Isolate patients with respiratory symptoms' if spike_detected else None,
            'Alert epidemiology team' if spike_detected else None,
            'Prepare additional ventilators' if spike_detected and breathing_count > 5 else None,
            'Activate pandemic protocols' if spike_detected else None
        ]
    })

@app.route('/api/condition-x-simulate', methods=['POST'])
def simulate_condition_x():
    for i in range(5):
        patient = {
            'name': f'Simulated Patient {i+1}',
            'phone': f'555000{i}',
            'symptoms': ['trouble breathing', 'cough', 'fever'],
            'duration': '2 days',
            'breathing_trouble': True,
            'triage_category': 'critical' if i < 2 else 'emergency',
            'status': 'waiting',
            'check_in_time': datetime.now(),
            'assigned_bed': None,
            'assigned_staff': None
        }
        patients_collection.insert_one(patient)
    
    return jsonify({'success': True, 'message': 'Simulated Condition X spike triggered'})

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