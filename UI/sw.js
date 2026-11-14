/**
 * UI/sw.js
 * ========
 * Cache-First Offline Service Worker for Whimsy CYOA Engine.
 *
 * Implements Issue #17 R5:
 * - Offline-capable PWA with Cache-First strategy.
 * - Pre-caches all essential static runtime assets, manifests, and scripts.
 * - Passes external cloud AI calls straight to network.
 */

const CACHE_NAME = 'cyoa-engine-v17';

const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './styles.css',
  './app.js',
  './manifest.json',
  './icon.png',
  './icon-512.png',
  './world_bible_data.json',
  './campaign_configs.json',
  './gameplay_manifest.json',
  './core/deterministic_core.js',
  './storage/indexeddb.js',
  './narrator/authored_narrator.js',
  './narrator/local_narrator.js',
  './narrator/cloud_narrator.js',
  './narrator/tiered_narrator.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// Cache-First strategy with network fallback for local static assets
self.addEventListener('fetch', (event) => {
  // Pass cloud and external API calls directly to network
  if (
    event.request.url.includes('googleapis.com') ||
    event.request.url.includes('openrouter.ai') ||
    event.request.method !== 'GET'
  ) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Return cached asset immediately
        return cachedResponse;
      }

      // If not in cache, fetch from network and cache for future offline use
      return fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const respClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, respClone);
            });
          }
          return networkResponse;
        })
        .catch(() => {
          // If offline and request is for navigation/HTML, return index.html
          if (event.request.mode === 'navigate' || event.request.headers.get('accept')?.includes('text/html')) {
            return caches.match('./index.html');
          }
        });
    })
  );
});
