# TriageFlow - Complete Setup Guide

## Prerequisites

Before starting, you need:
1. **Python installed** (version 3.8 or higher)
2. **MongoDB installed and running**
3. **Code editor** (VS Code recommended)

---

## Step 1: Install Python Dependencies

Open your terminal/command prompt and run:

```bash
pip install flask flask-cors pymongo apscheduler
```

Or create a `requirements.txt` file with:
```
flask
flask-cors
pymongo
apscheduler
```
Then run:
```bash
pip install -r requirements.txt
```

---

## Step 2: Set Up MongoDB

### Option A: Local MongoDB
1. Download MongoDB from https://www.mongodb.com/try/download/community
2. Install and run MongoDB service
3. Default connection: `mongodb://localhost:27017`

### Option B: MongoDB Atlas (Cloud)
1. Create free account at https://www.mongodb.com/atlas
2. Create free cluster
3. Get connection string
4. Update `config.py` with your connection string

---

## Step 3: Project Structure

Create this folder structure:
```
triageflow/
├── app.py              # Main Flask application
├── config.py           # Configuration (MongoDB connection)
├── README.md           # Documentation
├── static/
│   └── js/
│       └── dashboard.js
└── templates/
    ├── login.html
    ├── dashboard.html
    ├── patient_kiosk.html
    ├── patient_intake.html
    ├── my_patients.html
    ├── all_patients.html
    ├── staff.html
    ├── settings.html
    ├── bed_qr.html
    └── login-qr.html
```

---

## Step 4: Create Configuration File

Create `config.py`:
```python
import os

class Config:
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
    DATABASE_NAME = 'triageflow'
```

---

## Step 5: Create Main App (app.py)

This is the core file with all routes. Key sections:

### Imports (Lines 1-10)
```python
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
```

### Database Setup (Lines 15-27)
```python
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app, supports_credentials=True)

client = MongoClient(Config.MONGO_URI)
db = client[Config.DATABASE_NAME]

patients_collection = db['patients']
beds_collection = db['beds']
staff_collection = db['staff']
admins_collection = db['admins']
triage_logs_collection = db['triage_logs']
```

### Seed Data (Lines 55-85)
Creates 5 doctors (DTS001-005) and 5 nurses (NRS001-005) on first run.

### Routes
- `/login` - Login page
- `/dashboard` - Main dashboard
- `/patient-kiosk` - Patient self-check-in (no login)
- `/my-patients` - Doctor/Nurse's patients
- `/all-patients` - All patients
- `/staff` - Staff management
- `/settings` - Admin only
- `/bed-qr` - Bed QR codes
- `/login-qr` - QR code for login URL

### APIs
- `/api/submit-triage` - Submit patient check-in
- `/api/auto-assign` - Auto-assign doctor/nurse to patient
- `/api/beds` - Get all beds with patient info
- `/api/staff` - Get all staff
- `/api/patients` - Get all patients

---

## Step 6: Create HTML Templates

### Key Templates

1. **patient_kiosk.html** - Patient check-in form
   - Fields: Name, Age, Gender, Phone
   - Symptoms: 10 checkbox options
   - Duration: Dropdown
   - Yes/No Questions: Breathing, Family History, Substance Use, Sexually Active
   - All Yes/No buttons are BLUE

2. **dashboard.html** - Main hospital dashboard
   - Stats: Waiting, Admitted, Critical counts
   - Bed map with clickable beds
   - Patient list

3. **login.html** - Staff login
   - Two tabs: Staff Login / Admin Login
   - Staff ID field (DTS001 for doctors, NRS001 for nurses)
   - Admin ID field (ADMIN001)

---

## Step 7: Create JavaScript

### dashboard.js
- Loads beds and renders bed map
- Click on occupied bed shows patient info modal
- Patient assignment to beds

---

## Step 8: Run the Application

```bash
cd /path/to/triageflow
python app.py
```

You should see:
```
* Running on http://127.0.0.1:5000
```

---

## Step 9: Access the Application

Open your browser to: **http://127.0.0.1:5000**

### Login Credentials

| Role | ID | Password |
|------|-----|----------|
| Admin | ADMIN001 | admin123 |
| Doctor | DTS001 | any |
| Doctor | DTS002 | any |
| Nurse | NRS001 | any |
| Nurse | NRS002 | any |

### Patient Kiosk (No Login Required)
Go to: **http://127.0.0.1:5000/patient-kiosk**

---

## Key Features Implemented

### 1. Patient Triage System
- 4 categories: Simple, Attention, Emergency, Critical
- Auto-categorization based on symptoms

### 2. Staff ID System
- Doctors: DTS001, DTS002, etc.
- Nurses: NRS001, NRS002, etc.

### 3. Patient Balancing
- New patients assigned to doctor with fewest active patients
- Excludes discharged patients from count

### 4. Role-Based Access
- Admins see Settings link
- Doctors/Nurses redirected from Settings

### 5. Bed Management
- Click occupied bed to see patient details
- Shows: Name, Phone, Symptoms, Category, Doctors, Nurses

### 6. Patient Kiosk Updates
- Name, Age, Gender fields
- All Yes/No questions use BLUE buttons
- Ambulance prompt for Critical/Emergency

### 7. Login QR Code
- Access: `/login-qr`
- QR scans to: https://flow.niranjansj.club/login

---

## Common Issues & Solutions

### Issue: "Only 2 doctors getting all patients"
**Fix:** In `app.py`, convert staff _id to string before querying patients:
```python
doc_str_id = str(doc['_id'])
doc['current_count'] = patients_collection.count_documents({
    'assigned_doctors': doc_str_id,
    'status': {'$ne': 'discharged'}
})
```

### Issue: Bed patient info not showing
**Fix:** In `/api/beds`, look up patient by multiple methods:
```python
if b.get('patient_id'):
    patient = patients_collection.find_one({'_id': ObjectId(b['patient_id'])})
if not patient and b.get('bed_number'):
    patient = patients_collection.find_one({'assigned_bed': b['bed_number']})
```

---

## Quick Reference Commands

```bash
# Install dependencies
pip install flask flask-cors pymongo apscheduler

# Run the app
python app.py

# Access in browser
http://127.0.0.1:5000

# Patient kiosk (no login)
http://127.0.0.1:5000/patient-kiosk

# Login QR code
http://127.0.0.1:5000/login-qr
```

---

## File Summary

| File | Purpose | Lines |
|------|---------|-------|
| app.py | Main Flask app with all routes | ~860 |
| config.py | MongoDB configuration | ~10 |
| dashboard.html | Main dashboard template | ~160 |
| patient_kiosk.html | Patient check-in form | ~530 |
| dashboard.js | Dashboard JavaScript | ~420 |

---

*Last Updated: May 2, 2026*