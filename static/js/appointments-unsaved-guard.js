// appointments-unsaved-guard.js — extracted from templates/appointments.html (2026-09-26).
// Warn when the appointment modal closes / the tab closes with unsaved edits.
var apptModalSaved = false;
var apptModalDirty = false;

document.addEventListener('DOMContentLoaded', function () {
    const modalEl = document.getElementById('appointmentModal');
    const form = document.getElementById('appointmentForm');
    if (!modalEl || !form) return;

    const markDirty = function () { apptModalDirty = true; };
    form.addEventListener('input', markDirty);
    form.addEventListener('change', markDirty);

    // Reset flags each time the modal opens.
    modalEl.addEventListener('shown.bs.modal', function () {
        apptModalDirty = false;
        apptModalSaved = false;
    });

    // If it closes with edits and nothing was saved, say so plainly.
    modalEl.addEventListener('hidden.bs.modal', function () {
        if (apptModalDirty && !apptModalSaved) {
            showNotification('Appointment was not saved — your changes were discarded.', 'warning');
        }
        apptModalDirty = false;
        apptModalSaved = false;
    });
});

// Catch tab close / navigation while editing an appointment.
window.addEventListener('beforeunload', function (e) {
    if (apptModalDirty && !apptModalSaved) {
        e.preventDefault();
        e.returnValue = '';
    }
});

