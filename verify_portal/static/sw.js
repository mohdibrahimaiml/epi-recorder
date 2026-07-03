const CACHE_NAME = 'epi-verifier-v8';
const ASSETS = [
    './',
    './index.html',
    './verify/',
    './how-it-works.html',
    './pricing.html',
    './viewer/',
    './cases/',
    './css/epi.css',
    './js/epi-verify-core.js',
    './js/theme.js',
    './assets/logo.png',
    './assets/logo.svg',
    './manifest.json'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            // We try to cache local assets. External CDNs might be opaque/cors issues but we try.
            // For a robust offline app, we should bundle dependencies locally. 
            // For this MVP, we cache the main HTML which is most important.
            return cache.addAll([
                './',
                './index.html',
                './verify/',
                './how-it-works.html',
                './pricing.html',
                './viewer/',
                './cases/',
                './css/epi.css',
                './js/epi-verify-core.js',
                './js/theme.js',
                './assets/logo.png',
                './assets/logo.svg',
                './manifest.json'
            ]);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    // Clean up old caches if any
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
    // Network-First Strategy for HTML to ensure we always get the latest layout
    if (event.request.headers.get('accept').includes('text/html')) {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                    return response;
                })
                .catch(() => {
                    return caches.match(event.request);
                })
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
