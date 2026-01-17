const CACHE_NAME = 'epi-verifier-v3';
const ASSETS = [
    './verify.html',
    './manifest.json',
    './logo.svg',
    'https://esm.sh/@noble/ed25519@2.0.0'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            // We try to cache local assets. External CDNs might be opaque/cors issues but we try.
            // For a robust offline app, we should bundle dependencies locally. 
            // For this MVP, we cache the main HTML which is most important.
            return cache.addAll(['./verify.html', './manifest.json', './logo.svg']);
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
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            // Cache First strategy
            return cachedResponse || fetch(event.request);
        })
    );
});
