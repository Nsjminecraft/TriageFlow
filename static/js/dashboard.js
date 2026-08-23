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
                <button class="px-2 py-1.5 bg-purple-600 text-white rounded-lg text-xs hover:bg-purple-700" onclick="openAIInsights('${p._id}', '${(p.name || 'Patient').replace(/'/g, "\\'")}')" title="AI Insights">
                    <i class="fa-solid fa-brain"></i>
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
                    <div class="h-12 rounded-lg flex items-center justify-center text-xs font-semibold cursor-pointer hover:scale-105 transition-transform ${getBedClass(b.status)}" 
                        title="Bed ${b.bed_number} - ${b.type}"
                        onclick="${b.status === 'occupied' ? `showBedPatient('${b._id}', '${b.bed_number}')` : ''}"
                        ${b.status === 'occupied' ? 'style="cursor:pointer"' : ''}>
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

async function showBedPatient(bedId, bedNumber) {
    try {
        const response = await fetch('/api/beds');
        const beds = await response.json();
        const bed = beds.find(b => b._id === bedId);
        
        if (!bed || !bed.patient_info) {
            alert('No patient in this bed');
            return;
        }
        
        const p = bed.patient_info;
        const categoryColors = {
            simple: 'bg-green-100 text-green-700',
            attention: 'bg-yellow-100 text-yellow-700',
            emergency: 'bg-orange-100 text-orange-700',
            critical: 'bg-red-100 text-red-700'
        };
        
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-xl">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-xl font-bold text-gray-900"><i class="fa-solid fa-bed mr-2"></i>Bed ${bedNumber}</h3>
                    <button onclick="this.closest('.fixed').remove()" class="text-gray-400 hover:text-gray-600">
                        <i class="fa-solid fa-times text-xl"></i>
                    </button>
                </div>
                <div class="space-y-4">
                    <div class="bg-blue-50 p-4 rounded-lg">
                        <div class="font-semibold text-gray-900">Patient: ${p.name}</div>
                        <div class="text-sm text-gray-600">Phone: ${p.phone || 'N/A'}</div>
                        <div class="mt-2">
                            <span class="px-3 py-1 rounded-full text-sm font-medium ${categoryColors[p.triage_category] || 'bg-gray-100'}">
                                ${p.triage_category ? p.triage_category.charAt(0).toUpperCase() + p.triage_category.slice(1) : 'Unknown'}
                            </span>
                        </div>
                    </div>
                    <div>
                        <div class="font-semibold text-gray-700 mb-1">Symptoms:</div>
                        <div class="text-sm text-gray-600">${p.symptoms && p.symptoms.length > 0 ? p.symptoms.join(', ') : 'None listed'}</div>
                    </div>
                    <div>
                        <div class="font-semibold text-gray-700 mb-1">Status:</div>
                        <div class="text-sm text-gray-600 capitalize">${p.status || 'Unknown'}</div>
                    </div>
                    <div>
                        <div class="font-semibold text-gray-700 mb-1">Treating Doctors:</div>
                        <div class="text-sm text-gray-600">${p.doctors && p.doctors.length > 0 ? p.doctors.join(', ') : 'None assigned'}</div>
                    </div>
                    <div>
                        <div class="font-semibold text-gray-700 mb-1">Treating Nurses:</div>
                        <div class="text-sm text-gray-600">${p.nurses && p.nurses.length > 0 ? p.nurses.join(', ') : 'None assigned'}</div>
                    </div>
                    <div>
                        <div class="font-semibold text-gray-700 mb-1">Check-in Time:</div>
                        <div class="text-sm text-gray-600">${p.check_in_time ? new Date(p.check_in_time).toLocaleString() : 'Unknown'}</div>
                    </div>
                </div>
                <button onclick="this.closest('.fixed').remove()" class="mt-4 w-full px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 font-medium">
                    Close
                </button>
            </div>
        `;
        document.body.appendChild(modal);
    } catch (error) {
        console.error('Error loading patient info:', error);
        alert('Error loading patient info');
    }
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
    
    document.getElementById('modalTitle').textContent = 'Assign Patient';
    document.getElementById('assignModal').classList.remove('hidden');
    document.getElementById('assignModal').classList.add('flex');
    
    loadManualBedSelection();
}

async function loadManualBedSelection() {
    try {
        const response = await fetch('/api/beds');
        const beds = await response.json();
        const available = beds.filter(b => b.status === 'available');
        
        const container = document.getElementById('manualBedSelection');
        if (available.length === 0) {
            container.innerHTML = '<div class="col-span-4 text-center py-2 text-gray-400">No beds available</div>';
            return;
        }
        
        container.innerHTML = available.map(b => `
            <button type="button" class="px-2 py-2 border-2 border-gray-200 rounded-lg text-xs hover:border-blue-500 transition-all ${selectedBed === b._id ? 'bg-blue-600 text-white border-blue-600' : ''}"
                    onclick="selectManualBed('${b._id}', this)"
                    data-bed-number="${b.bed_number}">
                <div class="font-medium">${b.bed_number}</div>
                <div class="text-xs opacity-75">${b.wing}</div>
            </button>
        `).join('');
    } catch (error) {
        console.error('Error loading beds:', error);
    }
}

function selectManualBed(bedId, element) {
    selectedBed = bedId;
    document.querySelectorAll('#manualBedSelection button').forEach(btn => {
        btn.classList.remove('bg-blue-600', 'text-white', 'border-blue-600');
        btn.classList.add('border-gray-200');
    });
    element.classList.remove('border-gray-200');
    element.classList.add('bg-blue-600', 'text-white', 'border-blue-600');
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

async function manualAssign() {
    if (!selectedPatient) {
        alert('Please select a patient');
        return;
    }
    
    if (!selectedBed) {
        alert('Please select a bed manually');
        return;
    }
    
    try {
        const bedsRes = await fetch('/api/beds');
        const beds = await bedsRes.json();
        const selectedBedData = beds.find(b => b._id === selectedBed);
        
        if (selectedBedData) {
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

// ===== AI FEATURES =====
let currentAIPatientId = null;
let aiChatConversationHistory = [];
let globalChatHistory = [];

async function openAIInsights(patientId, patientName) {
    currentAIPatientId = patientId;
    aiChatConversationHistory = [];
    const modal = document.getElementById('aiInsightsModal');
    const content = document.getElementById('aiInsightsContent');
    const chatHistory = document.getElementById('aiChatHistory');
    chatHistory.classList.add('hidden');
    chatHistory.innerHTML = '';
    document.getElementById('aiChatInput').value = '';
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    content.innerHTML = '<div class="text-center py-8"><i class="fa-solid fa-spinner fa-spin text-3xl text-purple-500 mb-3"></i><p class="text-gray-500">Loading AI analysis...</p></div>';
    try {
        let res = await fetch('/api/ai-analysis/' + patientId);
        let data = await res.json();
        if (data.status === 'found' && data.analysis && data.analysis.status === 'completed') {
            renderDashboardAIAnalysis(data.analysis, patientName);
            return;
        }
    } catch(e) {}
    content.innerHTML = '<div class="text-center py-8"><i class="fa-solid fa-brain text-3xl text-purple-500 mb-3 animate-pulse"></i><p class="text-gray-500 font-medium">AI is analyzing ' + patientName + '...</p><p class="text-gray-400 text-sm mt-1">This may take 10-15 seconds</p></div>';
    try {
        let res = await fetch('/api/ai-analysis/' + patientId + '/generate', { method: 'POST' });
        let data = await res.json();
        if (data.success && data.analysis) {
            renderDashboardAIAnalysis(data.analysis, patientName);
        } else {
            content.innerHTML = '<div class="text-center py-8"><i class="fa-solid fa-triangle-exclamation text-3xl text-amber-500 mb-3"></i><p class="text-gray-600 font-medium">' + (data.error || 'AI analysis unavailable') + '</p><p class="text-gray-400 text-sm mt-2">Set OPENAI_API_KEY in .env file</p></div>';
        }
    } catch(e) {
        content.innerHTML = '<div class="text-center py-8"><i class="fa-solid fa-triangle-exclamation text-3xl text-red-500 mb-3"></i><p class="text-red-600">Error loading AI analysis</p></div>';
    }
}

function renderDashboardAIAnalysis(analysis, patientName) {
    const catColors = {simple:'bg-green-100 text-green-700 border-green-200',attention:'bg-yellow-100 text-yellow-700 border-yellow-200',emergency:'bg-orange-100 text-orange-700 border-orange-200',critical:'bg-red-100 text-red-700 border-red-200'};
    const catColor = catColors[analysis.recommended_category] || 'bg-gray-100 text-gray-700 border-gray-200';
    const confColor = analysis.confidence === 'high' ? 'text-green-600' : analysis.confidence === 'medium' ? 'text-yellow-600' : 'text-gray-500';
    let html = '<p class="text-sm text-gray-500 mb-4">AI clinical analysis for <strong>' + (patientName || 'Patient') + '</strong></p>';
    html += '<div class="border rounded-lg p-4 mb-4 ' + catColor + '"><div class="flex items-center justify-between mb-2"><span class="font-bold"><i class="fa-solid fa-stethoscope mr-1"></i>AI Recommended: ' + (analysis.recommended_category || '').toUpperCase() + '</span><span class="text-sm ' + confColor + ' font-medium">Confidence: ' + (analysis.confidence || '') + '</span></div><p class="text-sm">' + (analysis.reasoning || '') + '</p></div>';
    if (analysis.clinical_summary) { html += '<div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4"><p class="font-semibold text-blue-800 mb-1"><i class="fa-solid fa-notes-medical mr-1"></i>Clinical Summary</p><p class="text-sm text-blue-700">' + analysis.clinical_summary + '</p></div>'; }
    if (analysis.possible_conditions && analysis.possible_conditions.length > 0) {
        html += '<div class="mb-4"><p class="font-semibold text-gray-800 mb-2"><i class="fa-solid fa-magnifying-glass mr-1"></i>Possible Conditions</p><div class="space-y-2">';
        analysis.possible_conditions.forEach(function(c) { var lk = c.likelihood === 'high' ? 'bg-red-100 text-red-700' : c.likelihood === 'medium' ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600'; html += '<div class="flex items-center gap-2 text-sm bg-white rounded-lg p-2 border"><span class="px-2 py-0.5 rounded text-xs font-medium ' + lk + '">' + c.likelihood + '</span><span class="font-medium">' + c.name + '</span><span class="text-gray-400 ml-auto text-xs">' + (c.notes || '') + '</span></div>'; });
        html += '</div></div>';
    }
    if (analysis.suggested_tests && analysis.suggested_tests.length > 0) {
        html += '<div class="mb-4"><p class="font-semibold text-gray-800 mb-2"><i class="fa-solid fa-vial mr-1"></i>Suggested Tests</p><div class="space-y-1">';
        analysis.suggested_tests.forEach(function(t) { var pr = t.priority === 'urgent' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'; html += '<div class="flex items-center gap-2 text-sm"><span class="px-2 py-0.5 rounded text-xs font-medium ' + pr + '">' + t.priority + '</span><span class="font-medium">' + t.name + '</span><span class="text-gray-400 text-xs">- ' + (t.reason || '') + '</span></div>'; });
        html += '</div></div>';
    }
    if (analysis.risk_factors && analysis.risk_factors.length > 0) {
        html += '<div class="mb-4"><p class="font-semibold text-gray-800 mb-2"><i class="fa-solid fa-triangle-exclamation mr-1"></i>Risk Factors</p><div class="flex flex-wrap gap-2">';
        analysis.risk_factors.forEach(function(r) { html += '<span class="bg-amber-100 text-amber-700 px-3 py-1 rounded-full text-xs font-medium">' + r + '</span>'; });
        html += '</div></div>';
    }
    if (analysis.immediate_actions && analysis.immediate_actions.length > 0) {
        html += '<div class="bg-red-50 border border-red-200 rounded-lg p-4 mb-4"><p class="font-semibold text-red-800 mb-2"><i class="fa-solid fa-bolt mr-1"></i>Immediate Actions</p><ul class="text-sm text-red-700 space-y-1">';
        analysis.immediate_actions.forEach(function(a) { html += '<li>• ' + a + '</li>'; });
        html += '</ul></div>';
    }
    if (analysis.patient_instructions) { html += '<div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4"><p class="font-semibold text-green-800 mb-1"><i class="fa-solid fa-circle-info mr-1"></i>Patient Instructions</p><p class="text-sm text-green-700">' + analysis.patient_instructions + '</p></div>'; }
    if (analysis.red_flags && analysis.red_flags.length > 0) {
        html += '<div class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4"><p class="font-semibold text-amber-800 mb-2"><i class="fa-solid fa-flag mr-1"></i>Watch For</p><ul class="text-sm text-amber-700 space-y-1">';
        analysis.red_flags.forEach(function(r) { html += '<li>⚠️ ' + r + '</li>'; });
        html += '</ul></div>';
    }
    var modelLabel = analysis.model_used ? 'Powered by ' + analysis.model_used : 'AI-generated';
    html += '<p class="text-xs text-gray-400 text-center mt-4"><i class="fa-solid fa-robot mr-1"></i>' + modelLabel + ' clinical decision support • For medical staff reference only</p>';
    document.getElementById('aiInsightsContent').innerHTML = html;
}

function closeAIModal() {
    document.getElementById('aiInsightsModal').classList.add('hidden');
    document.getElementById('aiInsightsModal').classList.remove('flex');
}

async function sendAIChat() {
    const input = document.getElementById('aiChatInput');
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    const chatHistory = document.getElementById('aiChatHistory');
    chatHistory.classList.remove('hidden');
    chatHistory.innerHTML += '<div class="flex justify-end"><div class="bg-purple-600 text-white rounded-lg px-3 py-2 text-sm max-w-[80%]">' + message.replace(/</g,'&lt;') + '</div></div>';
    chatHistory.innerHTML += '<div class="flex gap-2" id="aiChatLoading"><div class="w-6 h-6 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0"><i class="fa-solid fa-robot text-purple-600 text-xs"></i></div><div class="bg-gray-100 rounded-lg px-3 py-2 text-sm"><i class="fa-solid fa-spinner fa-spin"></i> Thinking...</div></div>';
    chatHistory.scrollTop = chatHistory.scrollHeight;
    aiChatConversationHistory.push({ role: 'user', content: message });
    try {
        const res = await fetch('/api/ai-chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: message, patient_id: currentAIPatientId, history: aiChatConversationHistory.slice(0, -1) }) });
        const data = await res.json();
        const loading = document.getElementById('aiChatLoading');
        if (loading) loading.remove();
        if (data.success) {
            aiChatConversationHistory.push({ role: 'assistant', content: data.reply });
            const escaped = data.reply.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
            chatHistory.innerHTML += '<div class="flex gap-2"><div class="w-6 h-6 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0"><i class="fa-solid fa-robot text-purple-600 text-xs"></i></div><div class="bg-gray-100 rounded-lg px-3 py-2 text-sm max-w-[80%]">' + escaped + '</div></div>';
        } else { chatHistory.innerHTML += '<div class="text-red-500 text-xs">Error: ' + (data.error || 'Unknown') + '</div>'; }
    } catch(e) { const loading = document.getElementById('aiChatLoading'); if (loading) loading.remove(); chatHistory.innerHTML += '<div class="text-red-500 text-xs">Network error</div>'; }
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function openGlobalAIChat() {
    document.getElementById('globalAIChatModal').classList.remove('hidden');
    document.getElementById('globalAIChatModal').classList.add('flex');
    document.getElementById('globalChatInput').focus();
}
function closeGlobalAIChat() {
    document.getElementById('globalAIChatModal').classList.add('hidden');
    document.getElementById('globalAIChatModal').classList.remove('flex');
}

async function sendGlobalChat() {
    const input = document.getElementById('globalChatInput');
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    const messages = document.getElementById('globalChatMessages');
    messages.innerHTML += '<div class="flex justify-end gap-2"><div class="bg-purple-600 text-white rounded-lg p-3 text-sm max-w-[80%]">' + message.replace(/</g,'&lt;') + '</div></div>';
    messages.innerHTML += '<div class="flex gap-2" id="globalChatLoading"><div class="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0"><i class="fa-solid fa-robot text-purple-600 text-sm"></i></div><div class="bg-gray-100 rounded-lg p-3 text-sm"><i class="fa-solid fa-spinner fa-spin"></i> Thinking...</div></div>';
    messages.scrollTop = messages.scrollHeight;
    globalChatHistory.push({ role: 'user', content: message });
    try {
        const res = await fetch('/api/ai-chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: message, history: globalChatHistory.slice(0, -1) }) });
        const data = await res.json();
        const loading = document.getElementById('globalChatLoading');
        if (loading) loading.remove();
        if (data.success) {
            globalChatHistory.push({ role: 'assistant', content: data.reply });
            const escaped = data.reply.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
            messages.innerHTML += '<div class="flex gap-2"><div class="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0"><i class="fa-solid fa-robot text-purple-600 text-sm"></i></div><div class="bg-gray-100 rounded-lg p-3 text-sm max-w-[80%]">' + escaped + '</div></div>';
        } else { messages.innerHTML += '<div class="text-red-500 text-sm">Error: ' + (data.error || 'Unknown') + '</div>'; }
    } catch(e) { const loading = document.getElementById('globalChatLoading'); if (loading) loading.remove(); messages.innerHTML += '<div class="text-red-500 text-sm">Network error</div>'; }
    messages.scrollTop = messages.scrollHeight;
}

setInterval(() => {
    loadStats();
    loadPatients();
    loadBeds();
    loadStaff();
}, 10000);