// base-ui.js — extracted from templates/base.html (2026-09-26).
// Shared page behaviour for base.html: flash auto-dismiss, submit-button loading state, unsaved-changes guard (window.UnsavedGuard).
// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert[data-bs-dismiss="alert"]');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

// Add loading state to submit buttons (prevents double-submit) without
// ever locking the user out.
document.addEventListener('DOMContentLoaded', function() {
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            // If validation (native or a custom handler) blocked the
            // submit, do NOT show loading — otherwise the button stays
            // stuck on "Loading..." and can't be clicked again.
            if (e.defaultPrevented) return;
            if (typeof form.checkValidity === 'function' && !form.checkValidity()) return;

            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (!submitBtn) return;

            const originalHTML = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';

            // Safety net: if the page hasn't navigated away (slow/failed/
            // blocked submit), restore the button so the user isn't locked.
            setTimeout(function() {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalHTML;
            }, 10000);
        });
    });
});

// ── Unsaved-changes guard ───────────────────────────────────────────
// Warns before leaving a page with unsaved edits in a data-entry form.
// We deliberately do NOT cache form values to localStorage: this app
// handles patient PHI, and persisting it to the browser would leave
// sensitive data at rest on shared clinic machines.
(function () {
    let isDirty = false;
    let submitting = false;

    window.markFormClean = function () { isDirty = false; };

    function showBanner() {
        let banner = document.getElementById('unsavedBanner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'unsavedBanner';
            banner.style.cssText =
                'position:fixed;bottom:0;left:0;right:0;z-index:1080;' +
                'background:#fff3cd;color:#664d03;border-top:1px solid #ffecb5;' +
                'padding:8px 16px;text-align:center;font-size:14px;' +
                'box-shadow:0 -2px 6px rgba(0,0,0,.1);';
            banner.innerHTML =
                '<i class="fas fa-triangle-exclamation"></i> ' +
                'You have unsaved changes. Remember to save before leaving this page.';
            document.body.appendChild(banner);
        }
        banner.style.display = 'block';
        // Publish the banner's height so fixed bottom buttons (.save-btn)
        // can sit above it. Measured after display so wrapped text counts.
        document.documentElement.style.setProperty(
            '--unsaved-banner-h', banner.offsetHeight + 'px');
    }
    function hideBanner() {
        const banner = document.getElementById('unsavedBanner');
        if (banner) banner.style.display = 'none';
        document.documentElement.style.setProperty('--unsaved-banner-h', '0px');
    }

    // Shared API so JS-driven pages (e.g. the dental chart, which has no
    // <form> and saves via fetch) can hook into the same guard + banner.
    // resilient-submit.js uses markSubmitting() before an intentional
    // navigation and markDirty() when a save FAILED (which must re-arm the
    // leave-page warning even though a submit already happened).
    window.UnsavedGuard = {
        markDirty: function () {
            submitting = false;
            if (!isDirty) { isDirty = true; showBanner(); }
        },
        markClean: function () { isDirty = false; hideBanner(); },
        markSubmitting: function () { submitting = true; isDirty = false; hideBanner(); },
    };

    document.addEventListener('DOMContentLoaded', function () {
        // Guard only data-entry (POST) forms; skip GET search forms and
        // anything explicitly opted out with data-no-guard.
        const guarded = document.querySelectorAll(
            'form[method="post" i]:not([data-no-guard]), form[method="POST"]:not([data-no-guard])'
        );
        guarded.forEach(function (form) {
            const touch = function () {
                if (!isDirty) { isDirty = true; showBanner(); }
            };
            form.addEventListener('input', touch);
            form.addEventListener('change', touch);
            form.addEventListener('submit', function () {
                submitting = true;   // intentional navigation
                isDirty = false;
                hideBanner();
            });
        });
    });

    window.addEventListener('beforeunload', function (e) {
        if (isDirty && !submitting) {
            e.preventDefault();
            e.returnValue = '';   // triggers the browser's native confirm
        }
    });
})();

