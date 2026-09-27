// csrf-fetch.js — extracted from templates/base.html (2026-09-26).
// Adds the CSRF token to every state-changing fetch(). Loaded in <head> of base.html, before any other script.
(function () {
    const _fetch = window.fetch;
    window.fetch = function (resource, options) {
        options = options || {};
        const method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'PATCH', 'DELETE'].indexOf(method) !== -1) {
            const meta = document.querySelector('meta[name="csrf-token"]');
            const token = meta && meta.getAttribute('content');
            const headers = new Headers(options.headers || {});
            if (token && !headers.has('X-CSRFToken')) headers.set('X-CSRFToken', token);
            options.headers = headers;
        }
        return _fetch.call(this, resource, options);
    };
})();

