// appointments-new.js — extracted from templates/appointments.html (2026-09-26).
// Floating + button: open a blank New Appointment modal.
function openNewAppointment() {
    // Clear form
    document.getElementById('modalPatientName').value = '';
    // Local date (toISOString is UTC: "yesterday" in Manila until 8 AM).
    document.getElementById('modalAppointmentDate').value = formatDateForStorage(new Date());
    document.getElementById('modalAppointmentTime').value = '';
    document.getElementById('modalDuration').value = '30';
    document.getElementById('modalAppointmentType').value = 'checkup';
    document.getElementById('modalPriority').value = 'normal';
    document.getElementById('modalNotes').value = '';
    document.getElementById('appointmentForm').dataset.editingId = '';
    hideCancelButton();
    if (currentClinic) {
        document.getElementById('modalClinicSelect').value = currentClinic;
    } else {
        document.getElementById('modalClinicSelect').value = '';
    }
    new bootstrap.Modal(document.getElementById('appointmentModal')).show();
}

