const SW_VERSION = "__CACHE_BUST_VERSION__";
const CACHE_NAME = `recipe-clipper-shell-${SW_VERSION}`;

// Cache only static app-shell assets that are safe to serve offline.
const APP_SHELL = [
  "/",
  "/index.html",
  `/style.css?v=${SW_VERSION}`,
  `/app.js?v=${SW_VERSION}`,
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png"
];

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Always bypass cache for API responses so recipe and grocery data stays fresh.
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match("/index.html")));
    return;
  }

  const isVersionedFrontendAsset =
    url.origin === self.location.origin &&
    ["/style.css", "/app.js"].includes(url.pathname) &&
    url.searchParams.has("v");

  if (isVersionedFrontendAsset) {
    event.respondWith(
      fetch(req)
        .then((response) => {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, responseClone));
          return response;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  event.respondWith(caches.match(req).then((cached) => cached || fetch(req)));
});
