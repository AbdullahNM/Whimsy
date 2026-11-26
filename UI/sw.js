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

const STATIC_ASSET_PATHS = new Set(
  ASSETS_TO_CACHE.map((asset) => {
    try {
      return new URL(asset, self.location ? self.location.href : 'http://localhost/').pathname;
    } catch (e) {
      return asset.replace(/^\.\//, '/');
    }
  })
);

function isStaticAssetRequest(request) {
  if (!request || request.method !== 'GET') return false;
  let url;
  try {
    url = new URL(request.url);
  } catch (e) {
    return false;
  }
  if (self.location && url.origin !== self.location.origin) {
    return false;
  }
  const path = url.pathname;
  if (
    path.startsWith('/api/') ||
    path === '/health' ||
    path === '/status' ||
    path === '/generate' ||
    path === '/campaigns' ||
    path === '/campaign' ||
    path.startsWith('/telemetry') ||
    path.startsWith('/calibration') ||
    path.startsWith('/shadow') ||
    path.startsWith('/evaluate') ||
    path.startsWith('/v1/')
  ) {
    return false;
  }
  return STATIC_ASSET_PATHS.has(path) || path === '/' || path.endsWith('/index.html');
}

// Cache-First strategy restricted strictly to bundled static UI assets
self.addEventListener('fetch', (event) => {
  if (!isStaticAssetRequest(event.request)) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }

      return fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
            const respClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, respClone);
            });
          }
          return networkResponse;
        })
        .catch(() => {
          if (event.request.mode === 'navigate' || event.request.headers.get('accept')?.includes('text/html')) {
            return caches.match('./index.html');
          }
        });
    })
  );
});
