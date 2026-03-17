/**
 * R2-D2 Control System — Service Worker
 * Cache strategy:
 *   - Static assets (/static/*): cache-first
 *   - API calls (/status, /audio/*, etc.): network-first, fallback to cache
 * Cache name: r2d2-v1
 */

'use strict';

const CACHE = 'r2d2-v1';
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/manifest.json',
];

// ================================================================
// Install — pre-cache static assets
// ================================================================
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ================================================================
// Activate — clean up old cache versions
// ================================================================
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ================================================================
// Fetch — routing strategy
// ================================================================
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // POST requests and API calls: network-first, fallback to cache (or nothing)
  if (
    e.request.method === 'POST' ||
    url.pathname.startsWith('/audio') ||
    url.pathname.startsWith('/motion') ||
    url.pathname.startsWith('/status') ||
    url.pathname.startsWith('/servo') ||
    url.pathname.startsWith('/teeces') ||
    url.pathname.startsWith('/scripts') ||
    url.pathname.startsWith('/system') ||
    url.pathname.startsWith('/settings')
  ) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  // Static assets: cache-first, then network (and update cache)
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(resp => {
        // Only cache valid responses
        if (!resp || resp.status !== 200 || resp.type === 'opaque') {
          return resp;
        }
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return resp;
      });
    })
  );
});
