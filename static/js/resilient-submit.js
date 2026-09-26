// Resilient submit for long patient forms (create / edit).
//
// Why: a long PHI form can sit open for minutes. By the time it's submitted
// the connection may have been dropped somewhere between the device and the
// app (proxy idle timeout, flaky mobile link, host restart). Browsers silently
// retry a failed GET but NEVER a POST, so the user got Chrome's
// ERR_CONNECTION_CLOSED page, the typed patient was gone, and the server logged
// nothing (Incidents 2026-08-07 and 2026-09-26). Two other paths lost the form
// the same way: the 30-min idle logout and the 1-hour CSRF token expiry, both
// of which answered the POST with a redirect away from the form.
//
// What this does:
//   * sends the form via fetch and retries network failures with backoff
//     (create is idempotent server-side via submission_id, edit is a $set);
//   * asks the server for explicit JSON outcomes (X-Resilient-Submit header)
//     instead of guessing success from "it redirected";
//   * on an expired session/CSRF token: refreshes the token, or tells the user
//     to sign in in another tab — the form is never navigated away from;
//   * while the user is typing, pings /session/keepalive (throttled) so they
//     aren't idle-logged-out mid-form; no pings when nobody is typing;
//   * warns before leaving the page with unsaved entries.
// Nothing is written to device storage: typed PHI lives only in the open page.
//
// Usage: <form data-resilient-submit data-keepalive-url="..." data-login-url="...">
//   const rs = ResilientSubmit.attach(form);
//   ... in the submit handler, once the form is valid:
//   event.preventDefault(); rs.submit();
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

    function Controller(form) {
        this.form = form;
        this.keepaliveUrl = form.dataset.keepaliveUrl || '';
        this.loginUrl = form.dataset.loginUrl || '/login';
        this.button = form.querySelector('button[type="submit"]');
        this.dirty = false;
        this.leaving = false;
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
        window.addEventListener('beforeunload', (event) => {
            if (this.dirty && !this.leaving) {
                event.preventDefault();
                event.returnValue = '';
            }
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
                this.finish();
                this.showNetworkError();
            }
        );
    };

    Controller.prototype.handleResponse = function (res, tries, csrfRefreshed) {
        if (!isJson(res)) {
            // The server re-rendered the form (field validation, server error).
            // Let the browser post it natively and show that page as usual.
            this.nativeSubmit();
            return;
        }
        res.json().then((data) => {
            if (res.ok && data.ok && data.redirect) {
                this.leaving = true;
                window.location.replace(data.redirect);
            } else if (data.error === 'csrf' && !csrfRefreshed) {
                this.keepalive().then((ok) => {
                    if (ok) {
                        this.attempt(tries, true);
                    } else {
                        this.finish();
                        this.showSessionExpired();
                    }
                });
            } else if (data.error === 'session_expired' || data.error === 'csrf') {
                this.finish();
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
        this.leaving = true;
        this.form.submit();   // bypasses submit listeners, no recursion
    };

    Controller.prototype.finish = function () {
        this.inFlight = false;
        this.setBusy(false);
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
            'Nothing was lost — everything you typed is still here. '
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
            'Everything you typed is still here — do not close or reload this page. ',
            link,
            ', then come back to this tab and press Save again.',
        ]);
    };

    window.ResilientSubmit = {
        supported: supported,
        attach: function (form) {
            if (!form || !supported()) return null;
            if (!form._resilientSubmit) form._resilientSubmit = new Controller(form);
            return form._resilientSubmit;
        },
    };
})(window, document);
