// Resilient form submit — so a dropped connection or expired session never
// loses what someone typed.
//
// Why: a form can sit open for minutes. By the time it's submitted the
// connection may have been dropped somewhere between the device and the app
// (proxy idle timeout, flaky mobile link, host restart). Browsers silently
// retry a failed GET but NEVER a POST, so the user got Chrome's
// ERR_CONNECTION_CLOSED page, the typed data was gone, and the server logged
// nothing (Incidents 2026-08-07 and 2026-09-26). The 30-min idle logout and the
// 1-hour CSRF expiry lost forms the same way: both answered with a redirect.
//
// What this does:
//   * sends the form via fetch and retries network failures with backoff
//     (creates are idempotent server-side via submission_id; edits are $sets);
//   * asks the server for explicit JSON outcomes (X-Resilient-Submit header)
//     instead of guessing success from "it redirected";
//   * on an expired session/CSRF token: refreshes the token, or tells the user
//     to sign in in another tab — the page is never navigated away from;
//   * while the user is typing, pings /session/keepalive (throttled) so they
//     aren't idle-logged-out mid-form; no pings when nobody is typing;
//   * drives base.html's unsaved-changes guard (window.UnsavedGuard): a failed
//     save re-arms the banner + leave-page warning.
// Nothing is written to device storage: typed PHI lives only in the open page.
//
// Usage (loaded once by base.html):
//   * Simple forms: <form method="POST" data-resilient-submit="auto">. A create
//     form also carries <input type="hidden" name="submission_id">.
//   * Forms with their own JS validation: const rs = ResilientSubmit.attach(form);
//     then in the submit handler, once valid: event.preventDefault(); rs.submit();
// The route must answer a successful save with utils.submit_success(url).
(function (window, document) {
    'use strict';

    const HEADER = 'X-Resilient-Submit';
    const RETRY_DELAYS_MS = [1000, 2500, 5000];   // 4 attempts in all
    const KEEPALIVE_MIN_INTERVAL_MS = 4 * 60 * 1000;

    function supported() {
        return typeof window.fetch === 'function'
            && typeof window.FormData === 'function'
            && !!(window.crypto && window.crypto.getRandomValues);
    }

    function randomHexId() {
        const bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    }

    function isJson(res) {
        return (res.headers.get('Content-Type') || '').indexOf('application/json') !== -1;
    }

    // base.html's unsaved-changes guard; a no-op on pages without it.
    function guard(method) {
        const g = window.UnsavedGuard;
        if (g && typeof g[method] === 'function') g[method]();
    }

    function Controller(form) {
        const body = document.body.dataset;
        this.form = form;
        this.keepaliveUrl = form.dataset.keepaliveUrl || body.keepaliveUrl || '';
        this.loginUrl = form.dataset.loginUrl || body.loginUrl || '/login';
        this.button = form.querySelector('button[type="submit"]');
        this.dirty = false;
        this.inFlight = false;
        this.sessionExpired = false;
        this.lastPing = Date.now();

        form.addEventListener('input', () => {
            this.dirty = true;
            if (Date.now() - this.lastPing > KEEPALIVE_MIN_INTERVAL_MS) this.keepalive();
        });
        form.addEventListener('change', () => { this.dirty = true; });
        // Coming back to the tab (e.g. after signing in again in another one):
        // re-check the session and pick up a fresh CSRF token.
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && this.dirty) this.keepalive();
        });
    }

    Controller.prototype.submit = function () {
        if (this.inFlight) return;
        this.inFlight = true;
        this.setBusy(true);
        this.clearAlert();
        this.ensureSubmissionId();
        // After signing in again elsewhere the form's CSRF token is stale; the
        // server answers 'csrf' and handleResponse refreshes it and resends.
        this.attempt(0, false);
    };

    Controller.prototype.attempt = function (tries, csrfRefreshed) {
        const headers = {};
        headers[HEADER] = '1';
        headers.Accept = 'application/json';
        fetch(this.form.action, {
            method: 'POST',
            body: new FormData(this.form),
            credentials: 'same-origin',
            headers: headers,
        }).then(
            (res) => this.handleResponse(res, tries, csrfRefreshed),
            () => {
                // Network-level failure: nothing (or nothing we can see) reached
                // the server. Safe to resend — see header comment.
                if (tries < RETRY_DELAYS_MS.length) {
                    window.setTimeout(() => this.attempt(tries + 1, csrfRefreshed),
                                      RETRY_DELAYS_MS[tries]);
                    return;
                }
                this.fail();
                this.showNetworkError();
            }
        );
    };

    Controller.prototype.handleResponse = function (res, tries, csrfRefreshed) {
        if (!isJson(res)) {
            // The server answered with a page (a validation error, a server
            // error). Post natively so the browser shows that page as usual.
            this.nativeSubmit();
            return;
        }
        res.json().then((data) => {
            if (res.ok && data.ok && data.redirect) {
                guard('markSubmitting');            // intentional navigation
                window.location.replace(data.redirect);
            } else if (data.error === 'csrf' && !csrfRefreshed) {
                this.keepalive().then((ok) => {
                    if (ok) {
                        this.attempt(tries, true);
                    } else {
                        this.fail();
                        this.showSessionExpired();
                    }
                });
            } else if (data.error === 'session_expired' || data.error === 'csrf') {
                this.fail();
                this.sessionExpired = true;
                this.showSessionExpired();
            } else {
                this.nativeSubmit();
            }
        }).catch(() => this.nativeSubmit());
    };

    // Refresh the session's activity stamp + CSRF token. Resolves true when the
    // session is alive, false otherwise (never rejects).
    Controller.prototype.keepalive = function () {
        if (!this.keepaliveUrl) return Promise.resolve(true);
        this.lastPing = Date.now();
        const headers = {};
        headers[HEADER] = '1';
        headers.Accept = 'application/json';
        return fetch(this.keepaliveUrl, {
            credentials: 'same-origin',
            cache: 'no-store',
            headers: headers,
        }).then((res) => {
            if (res.status === 401) {
                this.sessionExpired = true;
                return false;
            }
            return res.json().then((data) => {
                if (!data.ok) return false;
                if (data.csrf_token) this.setCsrfToken(data.csrf_token);
                if (this.sessionExpired) {
                    this.sessionExpired = false;
                    this.clearAlert();
                }
                return true;
            });
        }).catch(() => false);   // offline blip: submit has its own retries
    };

    Controller.prototype.setCsrfToken = function (token) {
        const input = this.form.querySelector('input[name="csrf_token"]');
        if (input) input.value = token;
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) meta.setAttribute('content', token);
    };

    Controller.prototype.ensureSubmissionId = function () {
        const input = this.form.querySelector('input[name="submission_id"]');
        if (input && !input.value) input.value = randomHexId();
    };

    Controller.prototype.nativeSubmit = function () {
        guard('markSubmitting');
        this.form.submit();   // bypasses submit listeners, no recursion
    };

    // Nothing was saved: unlock the button and re-arm the unsaved-changes guard.
    Controller.prototype.fail = function () {
        this.inFlight = false;
        this.setBusy(false);
        guard('markDirty');
    };

    Controller.prototype.setBusy = function (busy) {
        const btn = this.button;
        if (!btn) return;
        if (busy) {
            btn.dataset.originalHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        } else {
            btn.disabled = false;
            if (btn.dataset.originalHtml) btn.innerHTML = btn.dataset.originalHtml;
        }
    };

    Controller.prototype.alertBox = function () {
        let box = this.form.querySelector('[data-resilient-alert]');
        if (!box) {
            box = document.createElement('div');
            box.setAttribute('data-resilient-alert', '');
            box.setAttribute('role', 'alert');
            this.form.insertBefore(box, this.form.firstChild);
        }
        return box;
    };

    Controller.prototype.clearAlert = function () {
        const box = this.form.querySelector('[data-resilient-alert]');
        if (box) box.replaceChildren();
    };

    Controller.prototype.showAlert = function (lines) {
        const box = this.alertBox();
        const alert = document.createElement('div');
        alert.className = 'alert alert-warning mb-3';
        lines.forEach((node) => alert.append(node));
        box.replaceChildren(alert);
        box.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    Controller.prototype.showNetworkError = function () {
        const strong = document.createElement('strong');
        strong.textContent = "Couldn't reach the server. ";
        this.showAlert([
            strong,
            'Nothing was lost — everything you entered is still here. '
            + 'Check the internet connection, then press Save again.',
        ]);
    };

    Controller.prototype.showSessionExpired = function () {
        const strong = document.createElement('strong');
        strong.textContent = 'You were signed out. ';
        const link = document.createElement('a');
        link.href = this.loginUrl;
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = 'Sign in again in a new tab';
        this.showAlert([
            strong,
            'Everything you entered is still here — do not close or reload this page. ',
            link,
            ', then come back to this tab and press Save again.',
        ]);
    };

    function attach(form) {
        if (!form || !supported()) return null;
        if (!form._resilientSubmit) form._resilientSubmit = new Controller(form);
        return form._resilientSubmit;
    }

    // Auto mode. A capture listener on the document runs BEFORE every form-level
    // submit handler (base.html's loading spinner + guard, page validators), so
    // the order is deterministic: invalid form -> step aside and let the page's
    // validation show; valid form -> take over the submit and own the button
    // + guard state.
    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || form.dataset.resilientSubmit !== 'auto') return;
        if (typeof form.checkValidity === 'function' && !form.checkValidity()) return;
        const controller = attach(form);
        if (!controller) return;             // very old browser: native submit
        event.preventDefault();
        event.stopImmediatePropagation();
        controller.submit();
    }, true);

    // Auto forms get keepalive-on-typing from page load, not just at submit.
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[data-resilient-submit="auto"]').forEach(attach);
    });

    window.ResilientSubmit = { supported: supported, attach: attach };
})(window, document);
