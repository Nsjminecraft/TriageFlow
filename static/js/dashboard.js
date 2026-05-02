let currentFilter = 'all';
let selectedPatient = null;
let selectedBed = null;
let selectedStaff = null;

async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) throw new Error('Stats failed');
        const stats = await response.json();
        document.getElementById('waitingCount').textContent = stats.patients.waiting;
        document.getElementById('admittedCount').textContent = stats.patients.admitted;
        document.getElementById('availableBeds').textContent = stats.beds.available;
        document.getElementById('availableStaff').textContent = stats.staff.available;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

let staffData = [];

async function loadPatients() {
    try {
        const [patientsRes, staffRes] = await Promise.all([
            fetch('/api/patients'),
            fetch('/api/staff')
        ]);
        if (!patientsRes.ok) throw new Error('Patients failed');
        const patients = await patientsRes.json();
        staffData = await staffRes.json();
        renderPatients(patients);
    } catch (error) {
        console.error('Error loading patients:', error);
        document.getElementById('patientsList').innerHTML = '<div class="text-center py-8 text-red-500">Error loading patients</div>';
    }
}

function getStaffNameById(staffId) {
    const staff = staffData.find(s => s._id === staffId);
    return staff ? staff.name : 'Unknown';
}

function renderPatients(patients) {
    const list = document.getElementById('patientsList');
    const filtered = currentFilter === 'all' 
        ? patients 
        : patients.filter(p => p.triage_category === currentFilter);
    
    if (filtered.length === 0) {
        list.innerHTML = '<div class="text-center py-8 text-gray-500">No patients in this category</div>';
        return;
    }
    
    list.innerHTML = filtered.map(p => `
        <div class="bg-white rounded-lg p-4 border border-gray-200 hover:border-blue-400 transition-all shadow-sm">
            <div class="flex items-center gap-3 mb-3">
                <div class="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold ${getCategoryColor(p.triage_category)} flex-shrink-0">
                    ${p.triage_category.charAt(0).toUpperCase()}
                </div>
                <div class="min-w-0">
                    <h4 class="font-semibold text-gray-900 truncate">${p.name || 'Anonymous'}</h4>
                    <p class="text-gray-400 text-xs">${formatTime(p.check_in_time)}</p>
                </div>
                <span class="px-2 py-1 rounded-full text-xs font-medium ${getCategoryBadge(p.triage_category)} ml-auto">${p.triage_category}</span>
            </div>
            <p class="text-gray-500 text-sm mb-3 truncate">${p.symptoms ? p.symptoms.join(', ') : 'No symptoms'}</p>
            <div class="flex flex-wrap gap-1 mb-3">
                ${p.assigned_doctors && p.assigned_doctors.length > 0 ? `<span class="text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded"><i class="fa-solid fa-user-md"></i> Dr.</span>` : ''}
                ${p.assigned_nurses && p.assigned_nurses.length > 0 ? `<span class="text-xs bg-green-50 text-green-600 px-2 py-1 rounded"><i class="fa-solid fa-user-nurse"></i> ${p.assigned_nurses.length}</span>` : ''}
                <span class="text-xs text-gray-400">${p.status}</span>
            </div>
            <div class="flex gap-2">
                <button class="flex-1 px-2 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700" onclick="openAssignModal('${p._id}')">
                    <i class="fa-solid fa-bed mr-1"></i> Assign
                </button>
                ${p.status === 'admitted' ? `<button class="flex-1 px-2 py-1.5 bg-green-600 text-white rounded-lg text-xs hover:bg-green-700" onclick="dischargePatient('${p._id}')"><i class="fa-solid fa-check"></i></button>` : ''}
            </div>
        </div>
    `).join('');
}

function getCategoryColor(category) {
    const colors = {
        simple: 'bg-green-500',
        attention: 'bg-yellow-500',
        emergency: 'bg-orange-500',
        critical: 'bg-red-600'
    };
    return colors[category] || 'bg-gray-500';
}

function getCategoryBadge(category) {
    const badges = {
        simple: 'bg-green-100 text-green-700',
        attention: 'bg-yellow-100 text-yellow-700',
        emergency: 'bg-orange-100 text-orange-700',
        critical: 'bg-red-100 text-red-700'
    };
    return badges[category] || 'bg-gray-100 text-gray-700';
}

function formatTime(isoString) {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

async function loadBeds() {
    try {
        const response = await fetch('/api/beds');
        if (!response.ok) throw new Error('Beds failed');
        const beds = await response.json();
        renderBeds(beds);
    } catch (error) {
        console.error('Error loading beds:', error);
        document.getElementById('bedGrid').innerHTML = '<div class="text-center py-8 text-red-500 col-span-5">Error loading beds</div>';
    }
}

function renderBeds(beds) {
    const container = document.getElementById('bedMapContainer');
    if (beds.length === 0) {
        container.innerHTML = '<div class="text-center py-8 text-gray-500">No beds configured</div>';
        return;
    }
    
    const wingsMap = {};
    beds.forEach(b => {
        if (!wingsMap[b.wing]) wingsMap[b.wing] = [];
        wingsMap[b.wing].push(b);
    });
    
    container.innerHTML = Object.entries(wingsMap).map(([wing, wingBeds]) => `
        <div class="mb-4">
            <div class="text-xs font-semibold text-gray-600 mb-2 flex items-center gap-2">
                <i class="fa-solid fa-building"></i> ${wing}
                <span class="text-gray-400">(${wingBeds.filter(b => b.status === 'available').length}/${wingBeds.length})</span>
            </div>
            <div class="grid grid-cols-6 sm:grid-cols-8 gap-2">
                ${wingBeds.map(b => `
                    <div class="h-12 rounded-lg flex items-center justify-center text-xs font-semibold cursor-pointer hover:scale-105 transition-transform ${getBedClass(b.status)}" title="Bed ${b.bed_number} - ${b.type}">
                        ${b.bed_number}
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

function getBedClass(status) {
    const classes = {
        available: 'bg-emerald-100 text-emerald-700 border-2 border-emerald-400',
        occupied: 'bg-red-100 text-red-700 border-2 border-red-400',
        cleaning: 'bg-amber-100 text-amber-700 border-2 border-amber-400'
    };
    return classes[status] || 'bg-gray-100 text-gray-700 border-2 border-gray-300';
}

async function loadStaff() {
    try {
        const response = await fetch('/api/staff');
        if (!response.ok) throw new Error('Staff failed');
        const staff = await response.json();
        renderStaff(staff);
    } catch (error) {
        console.error('Error loading staff:', error);
        document.getElementById('staffList').innerHTML = '<div class="text-center py-4 text-red-500">Error loading staff</div>';
    }
}

function renderStaff(staff) {
    const list = document.getElementById('staffList');
    const displayStaff = staff.slice(0, 5);
    
    if (displayStaff.length === 0) {
        list.innerHTML = '<div class="text-center py-4 text-gray-500 text-sm">No staff available</div>';
        return;
    }
    
    list.innerHTML = displayStaff.map(s => `
        <div class="flex items-center justify-between py-2 px-3 rounded-lg mb-1 ${getStaffBg(s.status)}">
            <div>
                <span class="text-sm font-medium">${s.name}</span>
                <span class="text-xs text-gray-500 ml-1">${s.role}</span>
            </div>
            <div class="text-xs">
                <span class="${s.patient_count > 0 ? 'text-blue-600 font-medium' : 'text-gray-400'}">${s.patient_count || 0}</span>
                <span class="text-gray-400"> patients</span>
            </div>
        </div>
    `).join('');
}

function getStaffBg(status) {
    const bgs = {
        available: 'bg-green-50',
        busy: 'bg-red-50',
        break: 'bg-amber-50',
        'off-duty': 'bg-gray-50'
    };
    return bgs[status] || 'bg-gray-50';
}

function openAssignModal(patientId) {
    selectedPatient = patientId;
    selectedBed = null;
    selectedStaff = null;
    
    document.getElementById('modalTitle').textContent = 'Assign Resources';
    document.getElementById('assignModal').classList.remove('hidden');
    document.getElementById('assignModal').classList.add('flex');
    
    loadAvailableBeds();
    loadAvailableStaff();
}

function closeModal() {
    document.getElementById('assignModal').classList.add('hidden');
    document.getElementById('assignModal').classList.remove('flex');
    selectedPatient = null;
    selectedBed = null;
    selectedStaff = null;
}

async function loadAvailableBeds() {
    try {
        const response = await fetch('/api/beds');
        const beds = await response.json();
        const available = beds.filter(b => b.status === 'available');
        
        const container = document.getElementById('bedSelection');
        if (available.length === 0) {
            container.innerHTML = '<p class="text-gray-500 col-span-3 text-center">No beds available</p>';
            return;
        }
        
        container.innerHTML = available.map(b => `
            <div class="px-3 py-2 border-2 border-gray-200 rounded-lg text-center cursor-pointer hover:border-blue-500 transition-all text-sm ${selectedBed === b._id ? 'bg-blue-600 text-white border-blue-600' : ''}" data-id="${b._id}" onclick="selectBed('${b._id}', this)">
                Bed ${b.bed_number}<br><small class="opacity-75">${b.wing || 'General'}</small>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading beds:', error);
    }
}

async function loadAvailableStaff() {
    try {
        const response = await fetch('/api/staff');
        const staff = await response.json();
        const available = staff.filter(s => s.status === 'available');
        
        const container = document.getElementById('staffSelection');
        if (available.length === 0) {
            container.innerHTML = '<p class="text-gray-500 col-span-3 text-center">No staff available</p>';
            return;
        }
        
        container.innerHTML = available.map(s => `
            <div class="px-3 py-2 border-2 border-gray-200 rounded-lg text-center cursor-pointer hover:border-blue-500 transition-all text-sm ${selectedStaff === s._id ? 'bg-blue-600 text-white border-blue-600' : ''}" data-id="${s._id}" onclick="selectStaff('${s._id}', this)">
                ${s.name}<br><small class="opacity-75">${s.role}</small>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading staff:', error);
    }
}

function selectBed(bedId, element) {
    document.querySelectorAll('#bedSelection > div').forEach(el => {
        el.classList.remove('bg-blue-600', 'text-white', 'border-blue-600');
        el.classList.add('border-gray-200');
    });
    element.classList.add('bg-blue-600', 'text-white', 'border-blue-600');
    element.classList.remove('border-gray-200');
    selectedBed = bedId;
}

function selectStaff(staffId, element) {
    document.querySelectorAll('#staffSelection > div').forEach(el => {
        el.classList.remove('bg-blue-600', 'text-white', 'border-blue-600');
        el.classList.add('border-gray-200');
    });
    element.classList.add('bg-blue-600', 'text-white', 'border-blue-600');
    element.classList.remove('border-gray-200');
    selectedStaff = staffId;
}

async function confirmAssignment() {
    if (!selectedPatient) {
        alert('Please select a patient');
        return;
    }
    
    try {
        if (selectedBed) {
            await fetch('/api/assign-bed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ patient_id: selectedPatient, bed_id: selectedBed })
            });
        }
        
        await fetch(`/api/auto-assign/${selectedPatient}`, { method: 'POST' });
        
        closeModal();
        loadPatients();
        loadBeds();
        loadStaff();
        loadStats();
    } catch (error) {
        console.error('Error assigning resources:', error);
        alert('Error assigning resources');
    }
}

async function dischargePatient(patientId) {
    if (!confirm('Are you sure you want to discharge this patient?')) return;
    
    try {
        await fetch('/api/discharge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ patient_id: patientId })
        });
        
        loadPatients();
        loadBeds();
        loadStaff();
        loadStats();
    } catch (error) {
        console.error('Error discharging patient:', error);
    }
}

document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.filter-btn').forEach(b => {
            b.classList.remove('bg-blue-600', 'text-white');
            b.classList.add('bg-white', 'text-gray-700');
        });
        this.classList.remove('bg-white', 'text-gray-700');
        this.classList.add('bg-blue-600', 'text-white');
        currentFilter = this.dataset.filter;
        loadPatients();
    });
});

loadStats();
loadPatients();
loadBeds();
loadStaff();

setInterval(() => {
    loadStats();
    loadPatients();
    loadBeds();
    loadStaff();
}, 10000);