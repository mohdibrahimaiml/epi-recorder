const CACHE_NAME = 'epi-verifier-v9';
const OFFLINE_PAGE = './offline.html';

const STATIC_ASSETS = [
    './',
    './index.html',
    './verify.html',
    './verify/index.html',
    './pricing.html',
    './scitt.html',
    './portal.html',
    './cases/index.html',
    './offline.html',
    './css/epi.css?v=24',
    './js/terminal.js',
    './js/dropzone.js?v=3',
    './assets/logo.png',
    './assets/logo.svg',
    './assets/epi-favicon.png',
    './assets/verifier-logo.png'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) =>
            cache.addAll(STATIC_ASSETS).catch((err) => {
                console.warn('[SW] Failed to pre-cache some assets:', err);
            })
        )
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

// Stale-While-Revalidate: serve from cache immediately, then refresh in background.
async function staleWhileRevalidate(request) {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);

    const fetchAndUpdate = fetch(request)
        .then((response) => {
            if (response && response.ok) {
                cache.put(request, response.clone());
            }
            return response;
        })
        .catch(() => cached);

    return cached || fetchAndUpdate;
}

// Network-First with cache fallback for HTML.
async function networkFirst(request) {
    const cache = await caches.open(CACHE_NAME);
    try {
        const response = await fetch(request);
        if (response && response.ok) {
            cache.put(request, response.clone());
        }
        return response;
    } catch (err) {
        const cached = await cache.match(request);
        if (cached) return cached;
        // Return offline page if we have it.
        const offline = await cache.match(OFFLINE_PAGE);
        return offline || new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
    }
}

self.addEventListener('fetch', (event) => {
    const { request } = event;
    const acceptHeader = request.headers.get('accept') || '';
    const url = new URL(request.url);

    // Skip non-GET requests and cross-origin fetches (e.g. Render backend, analytics).
    if (request.method !== 'GET' || url.origin !== self.location.origin) {
        return;
    }

    if (acceptHeader.includes('text/html')) {
        event.respondWith(networkFirst(request));
    } else {
        event.respondWith(staleWhileRevalidate(request));
    }
});
