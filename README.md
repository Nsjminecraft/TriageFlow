# TriageFlow - Hospital Dashboard System

A comprehensive hospital triage and patient management system built with Flask, MongoDB, and Tailwind CSS.

---

## Overview

**TriageFlow** is a hospital dashboard system designed for:
- Patient triage with 4 priority categories (Simple, Attention, Emergency, Critical)
- Staff management (Doctors and Nurses)
- Bed assignment and tracking
- Condition X monitoring and alerts
- Role-based access control

**Tech Stack:**
- Backend: Python Flask
- Database: MongoDB
- Frontend: HTML, Tailwind CSS, JavaScript
- Icons: Font Awesome 6

---

## What Was Done Today (Detailed)

### 1. Patient Kiosk Improvements

#### New Intake Questions Added
The patient-kiosk page now includes these additional questions:

| Question | Type | Description |
|----------|------|-------------|
| "Do you have a family history of this condition?" | Yes/No | Toggle buttons with color feedback |
| "Do you use tobacco, illicit drugs, or alcohol?" | Yes/No | Toggle buttons with color feedback |
| "Are you sexually active?" | Yes/No | Toggle buttons with color feedback |
| "What medications, vitamins, or supplements do you take?" | Text Area | Multi-line input |
| "Add Other Symptoms" | Expandable Button | Click to reveal additional text area |

#### Ambulance Prompt for Critical/Emergency Cases
- When a patient is categorized as **Critical** or **Emergency**, the result screen now asks:
  - *"Do you want us to call an ambulance for you?"*
- Two buttons:
  - **"Yes, call ambulance"** - Shows ambulance dispatched confirmation
  - **"No, I'll come myself"** - Shows directions to hospital emergency entrance

#### Contact Information Added
All result screens now include:
```
For further inquiries, call: 1-800-HELP-NOW
```

#### Backend Storage
Updated `/api/submit-triage` in `app.py` to store:
```python
family_history: family_history == 'yes',
substance_use: substance_use == 'yes',
sexually_active: sexually_active == 'yes',
medications: medications,
```

---

### 2. Staff ID System Redesign

#### Old System (Removed)
- All staff used IDs like `STF001`, `STF002`, etc.
- No distinction between doctors and nurses in ID

#### New System (Implemented)
- **Doctors**: `DTS001`, `DTS002`, `DTS003`, etc.
  - Prefix: `DTS` (Doctor)
  - 3-digit number with leading zeros
  
- **Nurses**: `NRS001`, `NRS002`, `NRS003`, etc.
  - Prefix: `NRS` (Nurse)
  - 3-digit number with leading zeros

#### Code Changes in `app.py`

**Seed Data (lines 55-70):**
```python
# Creates 5 doctors
for i in range(1, 6):
    staff_collection.insert_one({
        'staff_id': f'DTS{i:03d}',  # DTS001, DTS002...
        'name': f'Dr. Doctor {i}',
        'role': 'Doctor',
        ...
    })

# Creates 5 nurses
for i in range(1, 6):
    staff_collection.insert_one({
        'staff_id': f'NRS{i:03d}',  # NRS001, NRS002...
        'name': f'Nurse {i}',
        'role': 'Nurse',
        ...
    })
```

**Staff Creation API (lines 609-630):**
```python
if role == 'Doctor':
    doctor_count = staff_collection.count_documents({'role': 'Doctor'})
    staff_id = f'DTS{doctor_count + 1:03d}'
else:
    nurse_count = staff_collection.count_documents({'role': 'Nurse'})
    staff_id = f'NRS{nurse_count + 1:03d}'
```

---

### 3. Role-Based Access Control

#### Problem
All logged-in users could access all pages including Settings (which should be admin-only).

#### Solution
Added two new functions in `app.py`:

```python
def require_admin():
    return session.get('user_role') == 'Admin'
```

**Settings Page Protection:**
```python
@app.route('/settings')
def settings_page():
    if not require_login():
        return redirect('/login')
    if not require_admin():
        return redirect('/dashboard')
    return render_template('settings.html', user_role=session.get('user_role'))
```

#### Navigation Bar Changes
All templates now conditionally show/hide Settings based on role:
```html
{% if user_role == 'Admin' %}
<a href="/settings" class="...">Settings</a>
{% endif %}
```

**Pages updated:**
- dashboard.html
- all_patients.html
- my_patients.html
- staff.html
- condition_x.html
- settings.html
- bed_qr.html
- patient_intake.html

---

### 4. Consistent Navigation Bar

#### Problem
Each page had different navigation links and ordering.

#### Solution
Standardized all pages to have the same navbar:

**Doctor/Nurse View:**
```
[Dashboard] [My Patients] [Staff] [Condition X] [Bed QR] [All Patients] [Logout]
```

**Admin View:**
```
[Dashboard] [My Patients] [Staff] [Condition X] [Settings] [Bed QR] [All Patients] [Logout]
```

**Removed:**
- Patient Intake link (redundant - uses patient-kiosk instead)

**Pages updated:** All HTML templates in `/templates` folder

---

### 5. Patient Balancing Fix (Critical Bug Fix)

#### Problem
Only 1-2 doctors were getting ALL new patients, even when other doctors had 0 patients.

**Before Fix:**
- Doctor A (Staff Member 3): 8 patients
- Doctor B (Staff Member 5): 0 patients
- Doctor C (Staff Member 7): 0 patients
- New patient → Always assigned to Doctor A

#### Root Cause
In `app.py` line 435-438, the query compared MongoDB ObjectId to string:
```python
# BROKEN - compared ObjectId to string
doc['current_count'] = patients_collection.count_documents({
    'assigned_doctors': doc['_id'],  # ObjectId vs string mismatch!
    'status': {'$ne': 'discharged'}
})
```

#### Fix Applied
```python
# FIXED - convert to string first
doc_str_id = str(doc['_id'])
doc['current_count'] = patients_collection.count_documents({
    'assigned_doctors': doc_str_id,  # Now both are strings
    'status': {'$ne': 'discharged'}
})
```

**Same fix applied for nurses (lines 460-464).**

#### Results After Fix
```
Doctor: Staff Member 3  (STF003) - 8 patients (existing)
Doctor: Staff Member 5  (STF005) - 1 patient (just assigned)
Doctor: Staff Member 7  (STF007) - 0 patients (available)
Doctor: Staff Member 10 (STF010) - 0 patients (available)
```

New patients now correctly go to the doctor with the **fewest active patients** (excluding discharged patients).

---

### 6. Bed Patient Info Modal

#### Feature
Click on any **occupied bed** in the bed map to see detailed patient information.

#### Modal Content
```
┌─────────────────────────────────────────┐
│  Bed 7                                  │
├─────────────────────────────────────────┤
│  Patient: John Doe                      │
│  Phone: 555-1234                        │
│  Category: [Critical]                   │
│                                         │
│  Symptoms: chest pain, breathing...     │
│  Status: admitted                       │
│                                         │
│  Treating Doctors:                      │
│  Dr. Smith, Dr. Johnson                 │
│                                         │
│  Treating Nurses:                       │
│  Nurse Williams, Nurse Brown            │
│                                         │
│  Check-in Time:                         │
│  2026-05-02 14:20:04                    │
│                                         │
│  [Close]                                │
└─────────────────────────────────────────┘
```

#### Backend Changes
Updated `/api/beds` (lines 558-612) to include patient info:
```python
if b.get('patient_id'):
    patient = patients_collection.find_one({'_id': ObjectId(b['patient_id'])})
    # Get assigned doctors and nurses names
    for doc_id in patient.get('assigned_doctors', []):
        doc = staff_collection.find_one({'_id': ObjectId(doc_id)})
        doctors.append(doc.get('name', 'Unknown'))
```

#### Frontend Changes
Added `showBedPatient()` function in `dashboard.js`:
- Fetches all beds data
- Finds the clicked bed
- Displays modal with patient details
- Handles cases where patient might not be found

---

### 7. Login QR Code Page

#### Created
New page at `/login-qr` that displays a QR code.

#### Features
- QR code generated using qrcode.js library
- Scans to: `https://flow.niranjansj.club/login`
- Clean, centered design with TriageFlow branding

#### Files Created
- `templates/login-qr.html` - Contains HTML, CSS, and QR generation script

#### Route Added
```python
@app.route('/login-qr')
def login_qr_page():
    return render_template('login-qr.html')
```

---

## How to Run

### Prerequisites
- Python installed
- MongoDB running locally or remote
- Required packages: `flask`, `flask-cors`, `pymongo`, `apscheduler`

### Start the Application

```bash
cd "C:\Users\Intre\OneDrive\Desktop\lets do this shit"
python app.py
```

Then open: **http://127.0.0.1:5000**

### Login Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | ADMIN001 | admin123 |
| Doctor | DTS001 | (any password works) |
| Nurse | NRS001 | (any password works) |

### Important URLs
| Page | URL | Access |
|------|-----|--------|
| Login | /login | Everyone |
| Login QR | /login-qr | Everyone |
| Patient Kiosk | /patient-kiosk | Everyone (no login) |
| Dashboard | /dashboard | Logged in |
| My Patients | /my-patients | Doctor/Nurse |
| All Patients | /all-patients | Logged in |
| Staff | /staff | Logged in |
| Condition X | /condition-x | Logged in |
| Settings | /settings | Admin only |
| Bed QR | /bed-qr | Logged in |

---

## Key Files and Their Purpose

### Backend (`app.py`)
- **Lines 1-30**: Imports, Flask app setup, MongoDB connection
- **Lines 55-70**: Seed data for staff (creates 5 doctors, 5 nurses)
- **Lines 73-80**: Authentication helpers (`require_login`, `require_admin`)
- **Lines 100-160**: Route definitions (login, dashboard, settings, etc.)
- **Lines 347-420**: Triage submission API with new fields
- **Lines 430-530**: Auto-assign logic (fixed patient balancing)
- **Lines 558-612**: Beds API with patient info

### Templates (HTML)
| File | Purpose |
|------|---------|
| `login.html` | Staff/Admin login page |
| `dashboard.html` | Main hospital dashboard with bed map |
| `patient_kiosk.html` | Patient self-check-in (no login) |
| `patient_intake.html` | Staff patient intake form |
| `my_patients.html` | Doctor/Nurse's assigned patients |
| `all_patients.html` | All patients for today |
| `staff.html` | Staff management |
| `condition_x.html` | Condition X monitoring dashboard |
| `settings.html` | Hospital configuration (admin) |
| `bed_qr.html` | Bed QR code scanning |
| `login-qr.html` | QR code for login URL |

### JavaScript
| File | Purpose |
|------|---------|
| `dashboard.js` | Dashboard interactivity, bed clicking, patient assignment |
| `triage.js` | Patient intake form handling |

---

## Database Collections

### `patients`
```json
{
  "_id": "...",
  "name": "John Doe",
  "phone": "555-1234",
  "symptoms": ["chest pain", "breathing"],
  "triage_category": "critical",
  "status": "admitted",
  "assigned_doctors": ["doctor_id1"],
  "assigned_nurses": ["nurse_id1", "nurse_id2"],
  "assigned_bed": "7",
  "breathing_trouble": true,
  "family_history": false,
  "substance_use": false,
  "sexually_active": false,
  "medications": "aspirin",
  "check_in_time": "2026-05-02T..."
}
```

### `staff`
```json
{
  "_id": "...",
  "staff_id": "DTS001",
  "name": "Dr. Doctor 1",
  "role": "Doctor",
  "status": "busy",
  "shift": "morning"
}
```

### `beds`
```json
{
  "_id": "...",
  "bed_number": "7",
  "wing": "ICU",
  "type": "icu",
  "status": "occupied",
  "patient_id": "patient_id_here"
}
```

---

## Known Issues Resolved Today

1. ✅ Symptom checkboxes not clickable in patient-kiosk → Added click handlers
2. ✅ Only 2 doctors getting all patients → Fixed ObjectId vs string comparison
3. ✅ Patient info not showing on occupied beds → Fixed API to lookup by patient_id
4. ✅ Settings accessible by non-admins → Added admin role check
5. ✅ Inconsistent navbar across pages → Standardized all pages
6. ✅ Patient Intake link everywhere → Removed redundant link

---

## Next Steps / Improvements Needed

1. Condition X 24/7 monitoring with background scheduler
2. Patient discharge functionality for doctors
3. Proper session timeout handling
4. Add more validation on forms
5. Mobile-responsive improvements

---

*Last Updated: May 2, 2026*