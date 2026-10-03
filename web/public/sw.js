// @ts-check
// This URL replaces Wiki Copilot legacy's root worker. Only the public offline page is cached.
// SAFETY: browsers execute this file as a service worker, not a dedicated worker.
const worker = /** @type {ServiceWorkerGlobalScope & typeof self} */ (self);
const OFFLINE_CACHE = "wiki-copilot-offline-v1";
const OFFLINE_URL = "/offline.html";

worker.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(OFFLINE_CACHE).then(async (cache) => {
      const response = await fetch(OFFLINE_URL, { cache: "no-store" });
      if (!response.ok) throw new Error("Offline page unavailable");
      await cache.put(OFFLINE_URL, response);
      await worker.skipWaiting();
    })
  );
});

worker.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names
          .filter(
            (name) =>
              name.startsWith("wikicopilot-") ||
              (name.startsWith("wiki-copilot-offline-") &&
                name !== OFFLINE_CACHE)
          )
          .map((name) => caches.delete(name))
      );
      await worker.clients.claim();
    })()
  );
});

worker.addEventListener("fetch", (event) => {
  if (new URL(event.request.url).origin !== worker.location.origin) return;
  event.respondWith(
    fetch(event.request, { cache: "no-store" }).catch(
      async (/** @type {unknown} */ error) => {
        if (event.request.mode !== "navigate") {
          if (
            event.request.url.startsWith(`${worker.location.origin}/api/`) &&
            !(error instanceof DOMException && error.name === "AbortError")
          ) {
            const client = await worker.clients.get(event.clientId);
            client?.postMessage("wiki-copilot-offline");
          }
          throw error;
        }
        const cache = await caches.open(OFFLINE_CACHE);
        const offline = await cache.match(OFFLINE_URL);
        if (!offline) throw error;
        return offline;
      }
    )
  );
});
