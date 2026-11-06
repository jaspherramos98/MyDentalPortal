// appointments-visit.js — the calendar's "Record visit" dialog.
// Finishes a today/past visit in one step without leaving the calendar:
// pick the patient (bookings made by name only), tick records already entered
// for it, and/or add what was done. Saving marks the visit completed.
// Server: GET/POST /appointments/api/<id>/visit. Depends on appointments-page.js
// (dbPatients, refreshCalendar, editAppointment, setAppointmentStatus,
// showNotification). All user text goes in via textContent (never innerHTML).

const VisitDialog = (function () {
    let appointment = null;   // the calendar appointment being recorded
    let details = null;       // last GET response
    let submissionId = null;  // one per dialog open: a retried save can't double-create
    let modal = null;

    const $ = (id) => document.getElementById(id);
    const show = (el, on) => el.classList.toggle('d-none', !on);

    function newSubmissionId() {
        const bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);
        return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    }

    function formatDay(isoDay) {
        const d = new Date(isoDay + 'T00:00:00');
        return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    }

    function showError(message) {
        $('visitError').textContent = message;
        show($('visitError'), !!message);
    }

    function fillProcedures(procedures) {
        const select = $('visitProcedure');
        if (select.options.length) return;
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = 'Select procedure';
        select.appendChild(blank);
        procedures.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            select.appendChild(opt);
        });
    }

    function fillPatientPicker() {
        const select = $('visitPatientSelect');
        select.innerHTML = '';
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = 'Select patient';
        select.appendChild(blank);
        dbPatients.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            if (p.name.toLowerCase() === appointment.patientName.toLowerCase()) opt.selected = true;
            select.appendChild(opt);
        });
    }

    function renderCandidates(candidates) {
        const list = $('visitCandidateList');
        list.innerHTML = '';
        candidates.forEach(c => {
            const label = document.createElement('label');
            label.className = 'visit-candidate';
            const box = document.createElement('input');
            box.type = 'checkbox';
            box.className = 'form-check-input m-0';
            box.value = c.id;
            // One candidate = almost surely this visit's record (entered from the
            // patient page); with several, make the user choose rather than guess.
            box.checked = candidates.length === 1;
            box.addEventListener('change', updateSaveState);
            const text = document.createElement('span');
            const name = document.createElement('strong');
            name.textContent = c.procedure || 'Treatment';
            const when = document.createElement('span');
            when.className = 'text-muted small ms-2';
            when.textContent = formatDay(c.date);
            text.append(name, when);
            label.append(box, text);
            list.appendChild(label);
        });
        show($('visitCandidates'), candidates.length > 0);
        $('visitEntryTitle').textContent = candidates.length
            ? 'Add another procedure (optional)' : 'What was done';
    }

    function render(data) {
        details = data;
        fillProcedures(data.procedures || []);
        const a = data.appointment;
        $('visitPatientLabel').textContent = data.patient ? data.patient.name : a.patient_name;
        $('visitWhen').textContent = `${formatDay(a.date)} · ${formatTime(a.time)} · ${a.clinic_name}`;
        $('visitStateText').textContent = [data.visit.status_label, ...data.visit.reasons].join(' · ');
        document.querySelectorAll('.visit-currency').forEach(el => { el.textContent = data.currency; });

        show($('visitPickPatient'), !a.has_patient);
        renderCandidates(data.candidates || []);
        show($('visitEntry'), !!data.patient);
        show($('visitPriceNote'), !!data.price_needs_confirmation);
        const fullForm = $('visitFullFormLink');
        if (data.full_form_url) fullForm.href = data.full_form_url;
        show(fullForm, !!data.full_form_url);
        updateSaveState();
    }

    async function load(patientId) {
        show($('visitLoading'), true);
        showError('');
        let url = `/appointments/api/${encodeURIComponent(appointment.id)}/visit`;
        if (patientId) url += `?patient_id=${encodeURIComponent(patientId)}`;
        try {
            const response = await fetch(url);
            const data = await response.json();
            if (!data.success) {
                showError(data.error || 'Could not open this visit.');
                return;
            }
            render(data);
        } catch (error) {
            console.error('Load visit error:', error);
            showError("Couldn't reach the server. Check the connection and try again.");
        } finally {
            show($('visitLoading'), false);
        }
    }

    function checkedIds() {
        return Array.from($('visitCandidateList').querySelectorAll('input:checked'), b => b.value);
    }

    function updateSaveState() {
        const ready = details && details.patient &&
            (checkedIds().length > 0 || $('visitProcedure').value);
        $('visitSaveBtn').disabled = !ready;
    }

    function resetEntry() {
        ['visitProcedure', 'visitTooth', 'visitCharged', 'visitPaid', 'visitNotes']
            .forEach(id => { $(id).value = ''; });
    }

    async function save() {
        const procedure = $('visitProcedure').value;
        const payload = {
            patient_id: details.patient.id,
            link: checkedIds(),
            treatment: procedure ? {
                procedure: procedure,
                tooth_numbers: $('visitTooth').value,
                amount_charged: $('visitCharged').value,
                amount_paid: $('visitPaid').value,
                notes: $('visitNotes').value,
            } : null,
            submission_id: submissionId,
        };
        const btn = $('visitSaveBtn');
        btn.disabled = true;
        showError('');
        try {
            const response = await fetch(`/appointments/api/${encodeURIComponent(appointment.id)}/visit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json().catch(() => ({}));
            if (response.status === 401 || response.redirected) {
                showError('Your session ended. Log in again in another tab, then press Complete visit again.');
                return;
            }
            if (!data.success) {
                showError(data.error || 'Could not save the visit.');
                return;
            }
            modal.hide();
            await refreshCalendar();
            const v = data.visit;
            showNotification(v.reasons.length
                ? `Visit completed — still to do: ${v.reasons.join(', ')}.`
                : 'Visit completed.', v.reasons.length ? 'warning' : 'success');
        } catch (error) {
            console.error('Record visit error:', error);
            // Same submission id on the retry, so a save that did go through isn't duplicated.
            showError("Couldn't reach the server — nothing was lost. Press Complete visit again.");
        } finally {
            updateSaveState();
        }
    }

    async function markNoShow() {
        if (!confirm('Mark this appointment as a no-show?')) return;
        modal.hide();
        await setAppointmentStatus(appointment.id, 'no-show', 'Marked as no-show.');
    }

    function editBooking() {
        const appt = appointment;
        modal.hide();
        editAppointment(appt);
    }

    function open(appt) {
        appointment = appt;
        details = null;
        submissionId = newSubmissionId();
        resetEntry();
        $('visitPatientLabel').textContent = appt.patientName;
        $('visitWhen').textContent = '';
        $('visitStateText').textContent = '';
        ['visitPickPatient', 'visitCandidates', 'visitEntry'].forEach(id => show($(id), false));
        $('visitSaveBtn').disabled = true;
        if (!appt.patientId) fillPatientPicker();
        modal = modal || new bootstrap.Modal($('visitModal'));
        modal.show();
        const picked = !appt.patientId ? $('visitPatientSelect').value : '';
        load(picked);
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!$('visitModal')) return;
        $('visitSaveBtn').addEventListener('click', save);
        $('visitNoShowBtn').addEventListener('click', markNoShow);
        $('visitEditBtn').addEventListener('click', editBooking);
        $('visitProcedure').addEventListener('change', updateSaveState);
        $('visitPatientSelect').addEventListener('change', (e) => load(e.target.value));
    });

    return { open: open };
})();
