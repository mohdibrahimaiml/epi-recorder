const CACHE_NAME = 'epi-verifier-v9';
const ASSETS = [
    './',
    './index.html',
    './verify.html',
    './how-it-works.html',
    './technology.html',
    './use-cases.html',
    './demo.html',
    './pricing.html',
    './contact.html',
    './css/epi-v9.css',
    './js/app.js',
    './js/epi-verify-core.js',
    './assets/logo.png',
    './assets/logo.svg',
    './assets/sample.epi',
    './manifest.json'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        }).catch(() => {
            // If some assets fail (e.g., external), still complete install
            return caches.open(CACHE_NAME);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    const accept = req.headers.get('accept') || '';

    // Network-First for HTML to ensure fresh content
    if (accept.includes('text/html')) {
        event.respondWith(
            fetch(req)
                .then((response) => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
                    return response;
                })
                .catch(() => caches.match(req))
        );
        return;
    }

    // Stale-While-Revalidate for CSS/JS to get updates without waiting
    if (req.url.includes('.css') || req.url.includes('.js')) {
        event.respondWith(
            caches.match(req).then((cached) => {
                const fetchPromise = fetch(req).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const clone = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
                    }
                    return networkResponse;
                }).catch(() => cached);
                return cached || fetchPromise;
            })
        );
        return;
    }

    // Cache-First for static assets
    event.respondWith(
        caches.match(req).then((cachedResponse) => {
            return cachedResponse || fetch(req);
        })
    );
});
