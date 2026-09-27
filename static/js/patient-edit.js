// patient-edit.js — extracted from templates/patients/edit.html (2026-09-26).
// Patient edit form: contact-method rule + resilient submit (explicit mode).
(function () {
    const form = document.getElementById('editPatientForm');
    if (!form) return;
    // Attach now (not at submit) so keepalive + the unsaved-changes guard run
    // while the user is editing.
    const resilient = ResilientSubmit.attach(form);
    form.addEventListener('submit', function (e) {
        // Require at least one contact method (landline/cell/office/email) before save.
        const fields = Array.from(document.querySelectorAll('.contact-method'));
        const hasContact = fields.some(el => el.value.trim().length > 0);
        if (!hasContact) {
            e.preventDefault();
            fields.forEach(el => el.classList.add('is-invalid'));
            fields[0]?.focus();
            alert('Please provide at least one contact method (home, cell, or office phone, or email).');
            return;
        }
        fields.forEach(el => el.classList.remove('is-invalid'));
        // Send via fetch so a dropped connection or expired session never loses
        // the edits; native submit on very old browsers.
        if (resilient) {
            e.preventDefault();
            resilient.submit();
        }
    });
})();
