document.getElementById('triageForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const symptoms = formData.getAll('symptoms');
    
    const data = {
        name: formData.get('name'),
        phone: formData.get('phone'),
        symptoms: symptoms,
        duration: formData.get('duration'),
        breathing_trouble: formData.get('breathing_trouble') || 'no'
    };
    
    try {
        const response = await fetch('/api/submit-triage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showResult(result.category);
            e.target.reset();
        }
    } catch (error) {
        console.error('Error submitting triage:', error);
        alert('Error submitting triage. Please try again.');
    }
});

function showResult(category) {
    const modal = document.getElementById('resultModal');
    const badge = document.getElementById('resultBadge');
    const message = document.getElementById('resultMessage');
    
    const colors = {
        simple: 'bg-green-100 text-green-700',
        attention: 'bg-yellow-100 text-yellow-700',
        emergency: 'bg-orange-100 text-orange-700',
        critical: 'bg-red-100 text-red-700'
    };
    
    const labels = {
        simple: 'Simple - Home Care',
        attention: 'Attention - Wait < 2hrs',
        emergency: 'Emergency - See Doctor Now',
        critical: 'Critical - Direct to ICU'
    };
    
    badge.className = `px-6 py-2 rounded-full text-lg font-bold ${colors[category]}`;
    badge.textContent = labels[category];
    message.innerHTML = `You have been categorized as: <strong>${category.charAt(0).toUpperCase() + category.slice(1)}</strong>`;
    
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeResult() {
    const modal = document.getElementById('resultModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
    checkbox.addEventListener('change', function() {
        const box = this.nextElementSibling;
        if (this.checked) {
            box.classList.add('bg-blue-50', 'border-blue-500', 'text-blue-600');
        } else {
            box.classList.remove('bg-blue-50', 'border-blue-500', 'text-blue-600');
        }
    });
});

function selectBreathing(value) {
    document.querySelectorAll('input[name="breathing_trouble"]').forEach(r => {
        r.checked = (r.value === value);
        const label = r.closest('label');
        const box = label.querySelector('div');
        
        box.classList.remove('bg-red-50', 'bg-green-50', 'border-red-500', 'border-green-500', 'text-red-600', 'text-green-700', 'border-gray-200');
        box.classList.add('bg-white', 'border-gray-200');
        
        if (value === 'yes' && r.value === 'yes') {
            box.classList.remove('bg-white', 'border-gray-200');
            box.classList.add('bg-red-50', 'border-red-500', 'text-red-600');
        } else if (value === 'no' && r.value === 'no') {
            box.classList.remove('bg-white', 'border-gray-200');
            box.classList.add('bg-green-50', 'border-green-500', 'text-green-700');
        }
    });
}