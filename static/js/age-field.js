// age-field.js — fills an Age input from its Birthday input.
//
//   <input type="date" id="birthdate" ...>
//   <input name="age" data-age-from="birthdate" ...>
//
// With a valid birthday the age is computed and the field is read-only (the
// server recomputes it anyway — blueprints/ages.py). With no birthday the
// field stays editable for patients whose birth date is unknown. Fires an
// `input` event on the age field so listeners (e.g. the create form's
// minor/guardian check) react to the new value.
(function () {
    // Whole years between two 'YYYY-MM-DD' strings. Parsed by component, not
    // with new Date('YYYY-MM-DD') — that's UTC midnight and can land on the
    // previous day in the browser's timezone.
    function ageOn(birthday, today) {
        const b = /^(\d{4})-(\d{2})-(\d{2})$/.exec(birthday || '');
        if (!b) return null;
        const [, by, bm, bd] = b.map(Number);
        const ty = today.getFullYear(), tm = today.getMonth() + 1, td = today.getDate();
        let years = ty - by;
        if (tm < bm || (tm === bm && td < bd)) years--;
        return years >= 0 && years <= 150 ? years : null;
    }

    function bind(ageInput) {
        const birthInput = document.getElementById(ageInput.dataset.ageFrom);
        if (!birthInput) return;
        function sync() {
            const age = ageOn(birthInput.value, new Date());
            ageInput.readOnly = age !== null;
            ageInput.title = age !== null ? 'Calculated from the birthday' : '';
            if (age !== null && ageInput.value !== String(age)) {
                ageInput.value = age;
                ageInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }
        birthInput.addEventListener('input', sync);
        birthInput.addEventListener('change', sync);
        sync();
    }

    function init() {
        document.querySelectorAll('input[data-age-from]').forEach(bind);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
