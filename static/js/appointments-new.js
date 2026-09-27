// appointments-new.js — extracted from templates/appointments.html (2026-09-26).
// Floating + button: open a blank New Appointment modal.
function openNewAppointment() {
    // Clear form
    document.getElementById('modalPatientName').value = '';
    document.getElementById('modalAppointmentDate').value = new Date().toISOString().split('T')[0];
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

