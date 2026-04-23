const CACHE_NAME = "anidex-static-v8";
const CORE_ASSETS = [
    "/",
    "/index.html",
    "/manifest.webmanifest",
    "/static/styles.css",
    "/static/app.js",
    "/static/animals.js",
    "/static/anidex-icon.svg",
    "/static/vendor/tf.min.js",
    "/static/vendor/coco-ssd.min.js",
    "/static/vendor/coco-ssd/model.json",
    "/static/vendor/coco-ssd/group1-shard1of5",
    "/static/vendor/coco-ssd/group1-shard2of5",
    "/static/vendor/coco-ssd/group1-shard3of5",
    "/static/vendor/coco-ssd/group1-shard4of5",
    "/static/vendor/coco-ssd/group1-shard5of5",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") {
        return;
    }

    event.respondWith(
        caches.match(event.request).then((cached) => {
            if (cached) {
                return cached;
            }
            return fetch(event.request).then((response) => {
                const responseClone = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
                return response;
            });
        })
    );
});
