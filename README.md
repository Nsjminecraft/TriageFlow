# TriageFlow - Hospital Dashboard System

## What Was Done Today

### 1. Patient Kiosk Improvements
- Added new intake questions to patient-kiosk page:
  - Family history question (Yes/No)
  - Tobacco/drugs/alcohol use question (Yes/No)
  - Sexually active question (Yes/No)
  - Medications text field
  - "Other Symptoms" expandable text area
- Updated backend to store all new fields
- Made critical/emergency cases ask if patient wants ambulance called
- Added "For further inquiries call: 1-800-HELP-NOW" to result screens
- Restored symptom selection buttons (checkboxes) to match patient-intake

### 2. Staff ID System
- Changed staff ID format:
  - **Doctors**: DTS001, DTS002, DTS003... (DTS = Doctor)
  - **Nurses**: NRS001, NRS002, NRS003... (NRS = Nurse)
- Updated seed data to create 5 doctors (DTS001-005) and 5 nurses (NRS001-005)
- Updated staff creation API to use new ID format based on role

### 3. Role-Based Access Control
- Added `require_admin()` function to protect settings page
- Settings page now only accessible to Admins (doctors/nurses redirected to dashboard)
- Settings link hidden in navigation for non-admin users
- Added `user_role` variable to all template renders

### 4. Consistent Navigation Bar
- Made all pages have the same top navigation bar
- Removed "Patient Intake" from all pages (was redundant)
- Navbar order: Dashboard, My Patients, Staff, Condition X, Settings (Admin only), Bed QR, All Patients, Logout

### 5. Patient Balancing
- Fixed bug where only 1-2 doctors got all patients
- Issue: MongoDB ObjectId was being compared to string in patient count query
- Fix: Convert staff _id to string before querying patient assignments
- Now correctly counts patients per doctor/nurse and assigns to whoever has the fewest active patients (excluding discharged)

### 6. Bed Patient Info
- When clicking on an occupied bed, shows a modal with:
  - Patient name and phone
  - Triage category
  - Symptoms
  - Status
  - Treating doctors
  - Treating nurses
  - Check-in time
- Updated /api/beds to include patient info when bed is occupied

### 7. Login QR Code
- Created `/login-qr` page that displays a QR code
- QR code scans to: https://flow.niranjansj.club/login

## To Run the App
```bash
cd "C:\Users\Intre\OneDrive\Desktop\lets do this shit"
python app.py
```
Then open http://127.0.0.1:5000

## Default Login Credentials
- **Admin**: ADMIN001 / admin123
- **Staff IDs**: DTS001, DTS002, etc. (doctors) or NRS001, NRS002, etc. (nurses)

## Key Files
- `app.py` - Flask backend with all routes and APIs
- `templates/dashboard.html` - Main hospital dashboard
- `templates/patient_kiosk.html` - Patient check-in page (no login needed)
- `templates/my_patients.html` - Staff's assigned patients
- `templates/all_patients.html` - All today's patients
- `templates/settings.html` - Hospital configuration (admin only)
- `static/js/dashboard.js` - Dashboard JavaScript