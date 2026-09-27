// next-appointment-modal.js — extracted from templates/partials/_next_appointment_modal.html (2026-09-26).
// "Schedule Next Appointment" modal on treatment forms: creates a calendar appointment.
(function () {
    const saveBtn = document.getElementById('apptSaveBtn');
    if (!saveBtn) return;
    const errBox = document.getElementById('apptModalError');
    // Values come from data-* attributes on #nextApptModal (HTML-escaped by
    // Jinja, decoded by the browser) — never pasted into code.
    const cfg = document.getElementById('nextApptModal').dataset;
    const TODAY = cfg.today;

    saveBtn.addEventListener('click', async function () {
        errBox.classList.add('d-none');
        const date = document.getElementById('apptDate').value;
        const time = document.getElementById('apptTime').value;
        if (!date || !time) {
            errBox.textContent = 'Please choose a date and time.';
            errBox.classList.remove('d-none');
            return;
        }
        if (date < TODAY) {
            errBox.textContent = 'The appointment date cannot be in the past.';
            errBox.classList.remove('d-none');
            return;
        }
        const payload = {
            clinic_id: cfg.clinicId,
            patient_id: cfg.patientId,
            patient_name: cfg.patientName,
            date: date,
            time: time,
            duration: parseInt(document.getElementById('apptDuration').value),
            type: document.getElementById('apptType').value,
            notes: document.getElementById('apptNotes').value || '',
        };
        saveBtn.disabled = true;
        try {
            const resp = await fetch(cfg.createUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (data.success) {
                bootstrap.Modal.getInstance(document.getElementById('nextApptModal')).hide();
                const note = document.getElementById('apptScheduledNote');
                if (note) {
                    note.textContent = '✓ Scheduled for ' + date + ' at ' + time;
                    note.classList.remove('d-none');
                }
                const btn = document.getElementById('scheduleApptBtn');
                if (btn) {
                    btn.classList.replace('btn-outline-primary', 'btn-outline-success');
                    btn.innerHTML = '<i class="fas fa-calendar-check me-1"></i> Reschedule';
                }
            } else {
                errBox.textContent = data.error || 'Failed to schedule appointment.';
                errBox.classList.remove('d-none');
            }
        } catch (e) {
            errBox.textContent = 'Network error. Please try again.';
            errBox.classList.remove('d-none');
        } finally {
            saveBtn.disabled = false;
        }
    });
})();
