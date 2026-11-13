/* Service worker de INE Control.
   - Guarda en caché SOLO el armazón estático (HTML/CSS/JS/iconos) para que la app abra sin red.
   - NUNCA guarda respuestas de /api/ (pueden contener datos de documentos): siempre van a la red. */
"use strict";
const CACHE = "ine-control-v4";
const SHELL = ["/", "/static/styles.css", "/static/fixes.css", "/static/extra.css", "/static/app.js",
  "/static/icons/icon-192.png", "/static/icons/icon-512.png", "/static/icons/favicon-32.png", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  // Red primero (versión más reciente); si no hay red, armazón en caché.
  event.respondWith(fetch(event.request).then((resp) => {
    if (resp.ok && SHELL.includes(url.pathname)) {
      const copy = resp.clone();
      caches.open(CACHE).then((c) => c.put(event.request, copy));
    }
    return resp;
  }).catch(() => caches.match(event.request).then((hit) => hit || caches.match("/"))));
});
