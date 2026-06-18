const CACHE_NAME = 'epi-verifier-v8';
const ASSETS = [
    './',
    './index.html',
    './verify.html',
    './pricing.html',
    './scitt.html',
    './portal.html',
    './css/epi.css?v=24',
    './js/terminal.js',
    './js/dropzone.js?v=3',
    './assets/logo.png',
    './assets/logo.svg',
    './assets/epi-favicon.png'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
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
    const acceptHeader = event.request.headers.get('accept') || '';
    // Network-First Strategy for HTML to ensure we always get the latest layout
    if (acceptHeader.includes('text/html')) {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                    return response;
                })
                .catch(() => caches.match(event.request))
        );
    } else {
        // Cache-First for static assets
        event.respondWith(
            caches.match(event.request).then((cachedResponse) => {
                return cachedResponse || fetch(event.request);
            })
        );
    }
});
