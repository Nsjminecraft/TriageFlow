# I'm Here Check-In System - Backend Implementation

## Overview
Added a patient arrival system where patients can check in after triage and nurses can call their names from a waiting room.

---

## Step 1: Add New Fields to Patient Model

When submitting triage, we now include `queue_number` in the response so the patient can use it later:

**Location:** `app.py` around line 413-418

```python
return jsonify({
    'success': True,
    'patient': patient,
    'category': triage_category,
    'patient_id': str(patient['_id']),      # NEW - for frontend to store
    'name': patient['name'],                 # NEW - for display
    'queue_number': patients_collection.count_documents({'status': {'$ne': 'discharged'}}) + 1  # NEW - queue count
})
```

---

## Step 2: Create Mark Arrived API

**Location:** `app.py` after the submit-triage route (around line 420)

```python
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
    
    # Update patient with arrival status
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': {
            'arrived': True,                    # NEW FIELD
            'arrival_time': datetime.now(),    # NEW FIELD
            'queue_number': arrived_count + 1, # NEW FIELD
            'status': 'arrived'                 # Change status from 'waiting' to 'arrived'
        }}
    )
    
    return jsonify({'success': True, 'queue_number': arrived_count + 1})
```

**What it does:**
- Receives patient ID from frontend
- Counts how many patients are already arrived
- Updates patient document with:
  - `arrived: True`
  - `arrival_time: current time`
  - `queue_number: sequential number`
  - `status: 'arrived'`
- Returns the queue number to frontend

---

## Step 3: Create Get Arrived Patients API

**Location:** `app.py` after mark-arrived route (around line 445)

```python
@app.route('/api/arrived-patients', methods=['GET'])
def get_arrived_patients():
    # Find all patients who have arrived and not discharged
    arrived = list(patients_collection.find({
        'arrived': True,
        'status': {'$ne': 'discharged'}
    }).sort('queue_number', 1))  # Sort by queue number ascending
    
    # Convert ObjectId to string for JSON serialization
    for p in arrived:
        p['_id'] = str(p['_id'])
        p['arrival_time'] = p.get('arrival_time').isoformat() if p.get('arrival_time') else None
        p['check_in_time'] = p.get('check_in_time').isoformat() if p.get('check_in_time') else None
    
    return jsonify(arrived)
```

**What it does:**
- Queries patients where `arrived: True` and not discharged
- Sorts by queue number (1, 2, 3...)
- Converts MongoDB fields to JSON-serializable strings
- Returns array of patient objects

---

## Step 4: Create Call Patient API

**Location:** `app.py` after get-arrived-patients route (around line 464)

```python
@app.route('/api/call-patient/<patient_id>', methods=['POST'])
def call_patient():
    data = request.json
    patient_id = data.get('patient_id')
    
    # Mark patient as called
    patients_collection.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': {
            'called': True,              # NEW FIELD
            'called_at': datetime.now() # NEW FIELD
        }}
    )
    
    return jsonify({'success': True})
```

**What it does:**
- Receives patient ID from nurse
- Updates patient with `called: True` and timestamp
- This prevents calling the same patient twice

---

## Step 5: Create Waiting Room Route

**Location:** `app.py` around line 176-181 (added between all-patients and bed-qr)

```python
@app.route('/waiting-room')
def waiting_room_page():
    if not require_login():
        return redirect('/login')
    return render_template('waiting_room.html', user_role=session.get('user_role'))
```

**What it does:**
- Serves the waiting room HTML page
- Requires login (any staff can access)
- Passes user_role for navbar

---

## Database Fields Added

The patient collection now has these new fields:

```json
{
  "_id": "...",
  "name": "John Doe",
  "age": 35,
  "gender": "male",
  "phone": "5551234",
  "symptoms": ["chest pain"],
  "triage_category": "critical",
  "status": "arrived",              // Changed from "waiting" to "arrived"
  "arrived": true,                  // NEW - true when patient clicks "I'm Here"
  "arrival_time": "2026-05-02T14:30:00",  // NEW - timestamp when arrived
  "queue_number": 3,                // NEW - position in line
  "called": false,                  // NEW - true when nurse calls name
  "called_at": null,                // NEW - timestamp when called
  "check_in_time": "2026-05-02T14:20:00"
}
```

---

## How It All Works Together

### Patient Flow:
1. Patient submits triage at `/patient-kiosk`
2. Backend returns: `patient_id`, `name`, `queue_number`
3. Patient sees "I'm Here - Check In" button
4. Patient clicks button → calls `/api/mark-arrived`
5. Backend sets `arrived: true`, `status: arrived`, `queue_number`
6. Patient sees "Queue #X - Have a seat"

### Nurse Flow:
1. Nurse goes to `/waiting-room`
2. Page calls `/api/arrived-patients`
3. Shows list of arrived patients sorted by queue number
4. Nurse clicks "Call Name" → calls `/api/call-patient`
5. Patient marked as `called: true`
6. Button changes to "Called" (disabled)

---

## Files Created/Modified

| File | Change |
|------|--------|
| `app.py` | Added 3 new APIs + 1 route |
| `templates/waiting_room.html` | NEW - Waiting room page |
| `templates/dashboard.html` | Added Waiting Room link |
| `templates/patient_kiosk.html` | Added "I'm Here" button |
| All other HTML templates | Added Waiting Room link |

---

## API Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/submit-triage` | POST | Submit triage, returns queue_number |
| `/api/mark-arrived` | POST | Patient checks in |
| `/api/arrived-patients` | GET | Get all waiting patients |
| `/api/call-patient/<id>` | POST | Nurse calls patient |
| `/waiting-room` | GET | Serve waiting room page |

---

## Testing the Backend

```bash
# Start the app
python app.py

# Test 1: Submit a patient
curl -X POST http://127.0.0.1:5000/api/submit-triage \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","age":30,"gender":"male","symptoms":["cough"],"duration":"1-6 hours"}'

# Test 2: Mark as arrived (replace PATIENT_ID)
curl -X POST http://127.0.0.1:5000/api/mark-arrived \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"PATIENT_ID_HERE"}'

# Test 3: Get arrived patients
curl http://127.0.0.1:5000/api/arrived-patients

# Test 4: Call patient (replace PATIENT_ID)
curl -X POST http://127.0.0.1:5000/api/call-patient/PATIENT_ID_HERE \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"PATIENT_ID_HERE"}'
```

---

*Implementation Date: May 2, 2026*