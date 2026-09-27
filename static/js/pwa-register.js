// pwa-register.js — extracted from templates/base.html (2026-09-26).
// Registers the online-first service worker (static shell only, never PHI).
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js').catch(function (e) {
            console.warn('Service worker registration failed:', e);
        });
    });
}

