// MyDentalPortal service worker — online-first, app-shell-only caching.
//
// PHI safety: navigations (HTML) and data/API responses are NEVER cached —
// they always come from the network (single source of truth). Only same-origin
// STATIC shell assets are cached, for instant load. Bump CACHE to invalidate.
const CACHE = 'dp-shell-v1';
const SHELL = [
  '/static/css/main.css',
  '/static/js/main.js',
  '/static/offline.html',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;                  // never intercept writes
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // ignore cross-origin (CDN)

  // Navigations (HTML pages): network-only with an offline fallback. We never
  // cache authenticated pages — they may contain PHI.
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/static/offline.html')));
    return;
  }

  // Static shell assets: cache-first for instant load.
  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest') {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req).then((resp) => {
          if (resp && resp.ok && resp.type === 'basic') {
            const copy = resp.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return resp;
        });
      })
    );
    return;
  }

  // Everything else (data/API): straight to the network, never cached.
});
