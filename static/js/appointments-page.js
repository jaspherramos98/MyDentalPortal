// appointments-page.js — extracted from templates/appointments.html (2026-09-26).
// Appointments calendar: data, rendering, drag/drop, CRUD via /appointments/api.
// Global variables
let currentDate = new Date();
let draggedPatient = null;
let appointments = [];
let currentView = 'week'; // Default to week view
let currentClinic = ''; // Current selected clinic filter
let userClinics = []; // User's clinics

// Clinic + patient data from the #appointments-data JSON island (tojson-escaped
// by the template — values are never pasted into code, so names with quotes or
// backslashes are safe and display correctly).
const APPT_DATA = JSON.parse(document.getElementById('appointments-data').textContent);
const dbClinics = APPT_DATA.clinics;
const dbPatients = APPT_DATA.patients;

// API base URL for appointments
const API_URL = '/appointments/api';

// Initialize calendar
document.addEventListener('DOMContentLoaded', function() {
    userClinics = [...dbClinics];
    loadClinics();
    // Load real appointments from API
    loadAppointmentsFromAPI().then(() => {
        generateWeekView();
        setupDragAndDrop();
        setupSearch();
        setupClinicFilter();
        updateStats();
    });
});

// Fetch real appointments from backend API
async function loadAppointmentsFromAPI() {
    try {
        const today = new Date();
        const startOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
        const endOfMonth = new Date(today.getFullYear(), today.getMonth() + 2, 0);
        const start = startOfMonth.toISOString().split('T')[0];
        const end = endOfMonth.toISOString().split('T')[0];

        let url = `${API_URL}?start_date=${start}&end_date=${end}`;
        if (currentClinic) url += `&clinic_id=${currentClinic}`;

        const response = await fetch(url);
        const data = await response.json();

        if (data.success) {
            appointments = data.appointments.map(a => ({
                id: a.id,
                clinicId: a.clinic_id,
                patientId: a.patient_id,
                patientName: a.patient_name,
                date: a.date,
                time: a.time,
                duration: a.duration || 30,
                type: a.type || 'checkup',
                priority: a.priority || 'normal',
                notes: a.notes || '',
                status: a.status || 'scheduled'
            }));
        } else {
            appointments = [];
        }
    } catch (error) {
        console.error('Failed to load appointments:', error);
        appointments = [];
    }
}

function showWeekView() {
    currentView = 'week';
    document.getElementById('weekView').classList.add('active');
    document.getElementById('monthView').classList.remove('active');
    document.getElementById('weekViewBtn').classList.add('active');
    document.getElementById('monthViewBtn').classList.remove('active');
    generateWeekView();
}

function showMonthView() {
    currentView = 'month';
    document.getElementById('monthView').classList.add('active');
    document.getElementById('weekView').classList.remove('active');
    document.getElementById('monthViewBtn').classList.add('active');
    document.getElementById('weekViewBtn').classList.remove('active');
    generateMonthView();
}

function generateWeekView() {
    const grid = document.getElementById('weekGrid');
    const periodDisplay = document.getElementById('currentPeriod');
    
    // Get the start of the week (Sunday)
    const startOfWeek = new Date(currentDate);
    startOfWeek.setDate(currentDate.getDate() - currentDate.getDay());
    
    // Clear existing days (keep headers)
    const dayHeaders = grid.querySelectorAll('.day-header');
    grid.innerHTML = '';
    dayHeaders.forEach(header => grid.appendChild(header));
    
    // Update period display
    const endOfWeek = new Date(startOfWeek);
    endOfWeek.setDate(startOfWeek.getDate() + 6);
    periodDisplay.textContent = `Week of ${startOfWeek.toLocaleDateString('en-US', { 
        month: 'long', 
        day: 'numeric', 
        year: 'numeric' 
    })}`;
    
    // Generate 7 days for the week
    for (let i = 0; i < 7; i++) {
        const day = new Date(startOfWeek);
        day.setDate(startOfWeek.getDate() + i);
        
        const dayElement = createWeekDayElement(day);
        grid.appendChild(dayElement);
    }
}

function generateMonthView() {
    const grid = document.getElementById('calendarGrid');
    const periodDisplay = document.getElementById('currentPeriod');
    
    // Clear existing calendar days (keep headers)
    const dayHeaders = grid.querySelectorAll('.day-header');
    grid.innerHTML = '';
    dayHeaders.forEach(header => grid.appendChild(header));
    
    // Set month/year display
    periodDisplay.textContent = currentDate.toLocaleDateString('en-US', { 
        month: 'long', 
        year: 'numeric' 
    });
    
    // Get first day of month and number of days
    const firstDay = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
    const startDate = new Date(firstDay);
    startDate.setDate(startDate.getDate() - firstDay.getDay());
    
    // Generate calendar days
    for (let i = 0; i < 42; i++) {
        const day = new Date(startDate);
        day.setDate(startDate.getDate() + i);
        
        const dayElement = createMonthDayElement(day);
        grid.appendChild(dayElement);
    }
}

function createWeekDayElement(date) {
    const day = document.createElement('div');
    day.className = 'week-day';
    // Use local date string to avoid timezone issues
    day.dataset.date = formatDateForStorage(date);
    
    if (isToday(date)) {
        day.classList.add('today');
    }
    
    // Day header with date
    const dayHeader = document.createElement('div');
    dayHeader.className = 'day-number';
    dayHeader.innerHTML = `
        <strong>${date.getDate()}</strong><br>
        <small>${date.toLocaleDateString('en-US', { weekday: 'short' })}</small>
    `;
    day.appendChild(dayHeader);
    
    // Add appointments for this day (filtered by current clinic)
    const filteredAppointments = getFilteredAppointments();
    const dayAppointments = filteredAppointments.filter(apt => apt.date === day.dataset.date);
    dayAppointments.forEach(apt => {
        const appointmentElement = createAppointmentElement(apt);
        day.appendChild(appointmentElement);
    });
    
    // Make droppable
    setupDropZone(day);
    
    return day;
}

function createMonthDayElement(date) {
    const day = document.createElement('div');
    day.className = 'calendar-day';
    // Use local date string to avoid timezone issues
    day.dataset.date = formatDateForStorage(date);
    
    // Add classes for styling
    if (date.getMonth() !== currentDate.getMonth()) {
        day.classList.add('other-month');
    }
    
    if (isToday(date)) {
        day.classList.add('today');
    }
    
    // Day number
    const dayNumber = document.createElement('div');
    dayNumber.className = 'day-number';
    dayNumber.textContent = date.getDate();
    day.appendChild(dayNumber);
    
    // Add appointments for this day (filtered by current clinic)
    const filteredAppointments = getFilteredAppointments();
    const dayAppointments = filteredAppointments.filter(apt => apt.date === day.dataset.date);
    dayAppointments.forEach(apt => {
        const appointmentElement = createAppointmentElement(apt);
        day.appendChild(appointmentElement);
    });
    
    // Make droppable
    setupDropZone(day);
    
    return day;
}

function createAppointmentElement(appointment) {
    const apt = document.createElement('div');
    apt.className = `appointment-card ${appointment.type}`;
    if (appointment.status === 'cancelled') apt.classList.add('cancelled');
    apt.dataset.appointmentId = appointment.id;
    apt.dataset.clinicId = appointment.clinicId;
    
    const appointmentTime = document.createElement('div');
    appointmentTime.className = 'appointment-time';
    appointmentTime.textContent = formatTimeRange(appointment.time, appointment.duration);
    
    const appointmentPatient = document.createElement('div');
    appointmentPatient.className = 'appointment-patient';
    appointmentPatient.textContent = appointment.patientName;
    
    const appointmentType = document.createElement('div');
    appointmentType.className = `appointment-type ${appointment.type}`;
    appointmentType.textContent = appointment.type;
    
    // Add clinic name if in total view
    if (!currentClinic) {
        const clinicName = userClinics.find(c => c.id === appointment.clinicId)?.name || 'Unknown Clinic';
        const appointmentClinic = document.createElement('div');
        appointmentClinic.className = 'appointment-clinic';
        appointmentClinic.style.fontSize = '10px';
        appointmentClinic.style.color = '#666';
        // Icon as HTML, clinic name as a text node (never innerHTML) so a
        // crafted clinic name can't inject markup (DOM-XSS safe).
        appointmentClinic.innerHTML = '<i class="fas fa-building"></i> ';
        appointmentClinic.append(clinicName);
        apt.appendChild(appointmentClinic);
    }
    
    apt.appendChild(appointmentTime);
    apt.appendChild(appointmentPatient);
    apt.appendChild(appointmentType);

    if (appointment.status === 'cancelled') {
        const cancelledBadge = document.createElement('div');
        cancelledBadge.className = 'appointment-cancelled-badge';
        cancelledBadge.textContent = 'Cancelled';
        apt.appendChild(cancelledBadge);
    }

    // Click to edit
    apt.addEventListener('click', () => editAppointment(appointment));
    
    return apt;
}

function setupDragAndDrop() {
    const today = new Date().toISOString().split('T')[0];
    // Setup draggable patients (desktop) + tap-to-add (mobile/touch,
    // where HTML5 drag-and-drop doesn't fire). A plain click doesn't
    // fire after a real drag, so desktop dragging is unaffected.
    document.querySelectorAll('.patient-card').forEach(card => {
        card.addEventListener('dragstart', handleDragStart);
        card.addEventListener('dragend', handleDragEnd);
        card.addEventListener('click', function() {
            const patient = {
                id: this.dataset.patientId,
                name: this.dataset.patientName,
                phone: this.dataset.patientPhone,
            };
            const sel = document.getElementById('appointmentForm').dataset.selectedDate;
            showAppointmentModal(patient, sel || today);
        });
    });
}

function setupDropZone(dayElement) {
    dayElement.addEventListener('dragover', handleDragOver);
    dayElement.addEventListener('drop', handleDrop);
    dayElement.addEventListener('dragenter', handleDragEnter);
    dayElement.addEventListener('dragleave', handleDragLeave);
}

function handleDragStart(e) {
    draggedPatient = {
        id: this.dataset.patientId,
        name: this.dataset.patientName,
        phone: this.dataset.patientPhone
    };
    this.classList.add('dragging');
}

function handleDragEnd(e) {
    this.classList.remove('dragging');
}

function handleDragOver(e) {
    e.preventDefault();
}

function handleDragEnter(e) {
    e.preventDefault();
    this.classList.add('drop-zone');
}

function handleDragLeave(e) {
    if (!this.contains(e.relatedTarget)) {
        this.classList.remove('drop-zone');
    }
}

function handleDrop(e) {
    e.preventDefault();
    this.classList.remove('drop-zone');
    
    if (draggedPatient && !this.classList.contains('other-month')) {
        const selectedDate = this.dataset.date;
        showAppointmentModal(draggedPatient, selectedDate);
    }
}

function showAppointmentModal(patient, date) {
    const modal = new bootstrap.Modal(document.getElementById('appointmentModal'));
    
    // Pre-fill form with patient and date info
    document.getElementById('modalPatientName').value = patient.name;
    document.getElementById('modalAppointmentDate').value = date;
    
    // Set default clinic if filtering by clinic
    if (currentClinic) {
        document.getElementById('modalClinicSelect').value = currentClinic;
    } else {
        document.getElementById('modalClinicSelect').value = '';
    }
    
    // Clear other fields
    document.getElementById('modalAppointmentTime').value = '';
    document.getElementById('modalDuration').value = '30';
    document.getElementById('modalAppointmentType').value = 'checkup';
    document.getElementById('modalPriority').value = 'normal';
    document.getElementById('modalNotes').value = '';
    
    // Update selected date display. On phones use a compact format so the
    // badge width stays close to "Select a date" — the long weekday/month
    // string was far wider and reflowed the whole header (shoving the
    // calendar + legend down when you picked a patient). Desktop unchanged.
    const isPhone = window.matchMedia('(max-width: 768px), (max-height: 500px)').matches;
    const selectedDateFormatted = new Date(date + 'T00:00:00').toLocaleDateString(
        'en-US',
        isPhone
            ? { year: 'numeric', month: 'short', day: 'numeric' }
            : { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }
    );
    document.getElementById('selectedDate').textContent = selectedDateFormatted;
    
    // Store dragged patient info
    document.getElementById('appointmentForm').dataset.draggedPatient = JSON.stringify(patient);
    document.getElementById('appointmentForm').dataset.selectedDate = date;
    document.getElementById('appointmentForm').dataset.editingId = '';
    hideCancelButton();

    modal.show();
}

async function saveAppointment() {
    // Validation
    const patientName = document.getElementById('modalPatientName').value.trim();
    const appointmentDate = document.getElementById('modalAppointmentDate').value;
    const appointmentTime = document.getElementById('modalAppointmentTime').value;
    const appointmentType = document.getElementById('modalAppointmentType').value;
    const clinicId = document.getElementById('modalClinicSelect').value;
    
    if (!patientName || !appointmentDate || !appointmentTime || !appointmentType || !clinicId) {
        alert('Please fill in all required fields including clinic selection.');
        return;
    }

    const editingId = document.getElementById('appointmentForm').dataset.editingId;

    // Resolve patient_id from the entered name: link it only when the name
    // matches a registered patient. Otherwise leave it null so ad-hoc /
    // not-yet-registered walk-ins can still be booked by name without a
    // stale id from a previous drag getting attached to the wrong person.
    let resolvedPatientId = null;
    document.querySelectorAll('.patient-card').forEach(card => {
        if (card.dataset.patientName === patientName) {
            resolvedPatientId = card.dataset.patientId;
        }
    });

    const payload = {
        patient_name: patientName,
        date: appointmentDate,
        time: appointmentTime,
        type: appointmentType,
        clinic_id: clinicId,
        duration: parseInt(document.getElementById('modalDuration').value),
        priority: document.getElementById('modalPriority').value,
        notes: document.getElementById('modalNotes').value || '',
        patient_id: resolvedPatientId,
    };

    try {
        let response;
        if (editingId) {
            response = await fetch(`${API_URL}/${editingId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        } else {
            response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        }
        const data = await response.json();

        if (data.success) {
            await loadAppointmentsFromAPI();
            if (currentView === 'week') generateWeekView();
            else generateMonthView();
            updateStats();
            apptModalSaved = true;
            bootstrap.Modal.getInstance(document.getElementById('appointmentModal')).hide();
            const clinicName = userClinics.find(c => c.id === clinicId)?.name || 'Clinic';
            showNotification(editingId ? 'Appointment updated!' : `Appointment scheduled at ${clinicName}!`, 'success');
            document.getElementById('appointmentForm').dataset.editingId = '';
        } else {
            showNotification(data.error || 'Failed to save appointment', 'danger');
        }
    } catch (error) {
        console.error('Save appointment error:', error);
        showNotification('Failed to save appointment. Please try again.', 'danger');
    }
    draggedPatient = null;
}

function editAppointment(appointment) {
    const modal = new bootstrap.Modal(document.getElementById('appointmentModal'));
    
    // Pre-fill form with appointment data
    document.getElementById('modalClinicSelect').value = appointment.clinicId;
    document.getElementById('modalPatientName').value = appointment.patientName;
    document.getElementById('modalAppointmentDate').value = appointment.date;
    document.getElementById('modalAppointmentTime').value = appointment.time;
    document.getElementById('modalDuration').value = appointment.duration;
    document.getElementById('modalAppointmentType').value = appointment.type;
    document.getElementById('modalPriority').value = appointment.priority;
    document.getElementById('modalNotes').value = appointment.notes || '';
    
    // Store appointment ID for updates
    document.getElementById('appointmentForm').dataset.editingId = appointment.id;

    // Show + configure the Cancel/Reactivate button for existing appointments
    configureCancelButton(appointment.status);

    modal.show();
}

function configureCancelButton(status) {
    const btn = document.getElementById('cancelAppointmentBtn');
    if (!btn) return;
    btn.style.display = 'inline-block';
    if (status === 'cancelled') {
        btn.className = 'btn btn-outline-success me-auto';
        btn.innerHTML = '<i class="fas fa-rotate-left"></i> Reactivate Appointment';
        btn.dataset.targetStatus = 'scheduled';
    } else {
        btn.className = 'btn btn-outline-danger me-auto';
        btn.innerHTML = '<i class="fas fa-ban"></i> Cancel Appointment';
        btn.dataset.targetStatus = 'cancelled';
    }
}

function hideCancelButton() {
    const btn = document.getElementById('cancelAppointmentBtn');
    if (btn) btn.style.display = 'none';
}

async function cancelCurrentAppointment() {
    const editingId = document.getElementById('appointmentForm').dataset.editingId;
    if (!editingId) return;
    const btn = document.getElementById('cancelAppointmentBtn');
    const targetStatus = (btn && btn.dataset.targetStatus) || 'cancelled';
    const verb = targetStatus === 'cancelled' ? 'cancel' : 'reactivate';
    if (!confirm(`Are you sure you want to ${verb} this appointment?`)) return;
    try {
        const response = await fetch(`${API_URL}/${editingId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: targetStatus }),
        });
        const data = await response.json();
        if (data.success) {
            await loadAppointmentsFromAPI();
            if (currentView === 'week') generateWeekView();
            else generateMonthView();
            updateStats();
            apptModalSaved = true;
            bootstrap.Modal.getInstance(document.getElementById('appointmentModal')).hide();
            showNotification(
                targetStatus === 'cancelled' ? 'Appointment cancelled.' : 'Appointment reactivated.',
                'warning'
            );
            document.getElementById('appointmentForm').dataset.editingId = '';
        } else {
            showNotification(data.error || 'Failed to update appointment', 'danger');
        }
    } catch (error) {
        console.error('Cancel appointment error:', error);
        showNotification('Failed to update appointment', 'danger');
    }
}

async function deleteAppointment(appointmentId) {
    if (confirm('Are you sure you want to delete this appointment?')) {
        try {
            const response = await fetch(`${API_URL}/${appointmentId}`, { method: 'DELETE' });
            const data = await response.json();
            if (data.success) {
                await loadAppointmentsFromAPI();
                if (currentView === 'week') generateWeekView();
                else generateMonthView();
                updateStats();
                showNotification('Appointment deleted successfully!', 'warning');
            } else {
                showNotification(data.error || 'Failed to delete', 'danger');
            }
        } catch (error) {
            console.error('Delete error:', error);
            showNotification('Failed to delete appointment', 'danger');
        }
    }
}

function previousPeriod() {
    if (currentView === 'week') {
        currentDate.setDate(currentDate.getDate() - 7);
        generateWeekView();
    } else {
        currentDate.setMonth(currentDate.getMonth() - 1);
        generateMonthView();
    }
}

function nextPeriod() {
    if (currentView === 'week') {
        currentDate.setDate(currentDate.getDate() + 7);
        generateWeekView();
    } else {
        currentDate.setMonth(currentDate.getMonth() + 1);
        generateMonthView();
    }
}

async function goToToday() {
    currentDate = new Date();
    await loadAppointmentsFromAPI();
    if (currentView === 'week') {
        generateWeekView();
    } else {
        generateMonthView();
    }
    updateStats();
}

function setupSearch() {
    const searchInput = document.getElementById('patientSearch');
    const typeFilter = document.getElementById('appointmentTypeFilter');
    
    searchInput.addEventListener('input', filterPatients);
    typeFilter.addEventListener('change', filterAppointments);
}

function setupClinicFilter() {
    const clinicSelector = document.getElementById('clinicSelector');
    clinicSelector.addEventListener('change', function() {
        currentClinic = this.value;
        updateViewBadge();
        updateStats();
        
        // Refresh current view
        if (currentView === 'week') {
            generateWeekView();
        } else {
            generateMonthView();
        }
    });
}

function loadClinics() {
    const clinicSelector = document.getElementById('clinicSelector');
    const modalClinicSelect = document.getElementById('modalClinicSelect');
    
    // Clear existing options (except "All Clinics")
    modalClinicSelect.innerHTML = '<option value="">Select a clinic</option>';
    
    userClinics.forEach(clinic => {
        // Add to filter dropdown
        const filterOption = document.createElement('option');
        filterOption.value = clinic.id;
        filterOption.textContent = clinic.name;
        clinicSelector.appendChild(filterOption);
        
        // Add to modal dropdown
        const modalOption = document.createElement('option');
        modalOption.value = clinic.id;
        modalOption.textContent = clinic.name;
        modalClinicSelect.appendChild(modalOption);
    });
}

function getFilteredAppointments() {
    if (!currentClinic) {
        return appointments; // Return all appointments
    }
    return appointments.filter(apt => apt.clinicId === currentClinic);
}

function updateViewBadge() {
    const badge = document.getElementById('currentViewBadge');
    if (currentClinic) {
        const clinicName = userClinics.find(c => c.id === currentClinic)?.name || 'Unknown Clinic';
        // Clinic name as a text node (not innerHTML) — DOM-XSS safe.
        badge.innerHTML = '<i class="fas fa-building"></i> ';
        badge.append(clinicName);
    } else {
        badge.innerHTML = `<i class="fas fa-building"></i> All Clinics`;
    }
}

function filterPatients() {
    const searchTerm = document.getElementById('patientSearch').value.toLowerCase();
    const patientCards = document.querySelectorAll('.patient-card');
    
    patientCards.forEach(card => {
        const patientName = card.querySelector('.patient-name').textContent.toLowerCase();
        if (patientName.includes(searchTerm)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

function filterAppointments() {
    const typeFilter = document.getElementById('appointmentTypeFilter').value;
    const appointmentCards = document.querySelectorAll('.appointment-card');
    
    appointmentCards.forEach(card => {
        if (!typeFilter || card.classList.contains(typeFilter)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

function updateStats() {
    const today = formatDateForStorage(new Date());
    const filteredAppointments = getFilteredAppointments();
    
    const todayAppointments = filteredAppointments.filter(apt => apt.date === today).length;
    const totalSlots = 12; // Assuming 12 slots per day
    const availableSlots = totalSlots - todayAppointments;
    const totalAppointments = filteredAppointments.length;
    
    document.getElementById('todayAppointments').textContent = todayAppointments;
    document.getElementById('availableSlots').textContent = Math.max(0, availableSlots);
    document.getElementById('totalAppointments').textContent = totalAppointments;
    document.getElementById('clinicCount').textContent = userClinics.length;
    
    // Update labels based on current filter
    if (currentClinic) {
        const clinicName = userClinics.find(c => c.id === currentClinic)?.name || 'Selected Clinic';
        document.getElementById('todayLabel').textContent = 'Today at This Clinic';
        document.getElementById('totalLabel').textContent = 'Total at This Clinic';
    } else {
        document.getElementById('todayLabel').textContent = 'Today\'s Appointments';
        document.getElementById('totalLabel').textContent = 'Total Appointments';
    }
}

// Add this new utility function for consistent date formatting
function formatDateForStorage(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('show');
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 100px; right: 20px; z-index: 9999; min-width: 300px;';
    // Message as a text node (not innerHTML) so any user-derived content in
    // it (e.g. a clinic name) can't inject markup — DOM-XSS safe. The close
    // button is the only HTML.
    notification.append(message);
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close';
    closeBtn.setAttribute('data-bs-dismiss', 'alert');
    notification.appendChild(closeBtn);
    
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Utility functions
function isToday(date) {
    const today = new Date();
    return date.toDateString() === today.toDateString();
}

function formatTime(timeString) {
    if (!timeString) return '';

    const time = timeString.split(':');
    const hours = parseInt(time[0]);
    const minutes = time[1];
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    return `${displayHours}:${minutes} ${ampm}`;
}

// Show the booked window, e.g. "2:00 PM – 4:00 PM", from start + duration (minutes).
function formatTimeRange(timeString, duration) {
    if (!timeString) return '';
    const start = formatTime(timeString);
    const parts = timeString.split(':');
    const startMin = parseInt(parts[0]) * 60 + parseInt(parts[1]);
    let endMin = startMin + (parseInt(duration) || 30);
    endMin = ((endMin % 1440) + 1440) % 1440; // wrap within the day
    const eh = String(Math.floor(endMin / 60)).padStart(2, '0');
    const em = String(endMin % 60).padStart(2, '0');
    return `${start} – ${formatTime(eh + ':' + em)}`;
}

// Handle window resize for mobile
window.addEventListener('resize', function() {
    if (window.innerWidth > 768) {
        document.getElementById('sidebar').classList.remove('show');
    }
});

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function(e) {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.querySelector('.mobile-toggle');
    
    if (window.innerWidth <= 768 && 
        sidebar.classList.contains('show') && 
        !sidebar.contains(e.target) && 
        !toggleBtn.contains(e.target)) {
        sidebar.classList.remove('show');
    }
});

