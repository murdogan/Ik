const CACHE_PREFIX = "wealthy-falcon-hr-static-";
const CACHE_NAME = `${CACHE_PREFIX}v1`;
const NEXT_STATIC_PREFIX = "/_next/static/";
const ICON_PATHS = new Set([
  "/icon-192.png",
  "/icon-512.png",
  "/icon-maskable-512.png",
]);
const BLOCKED_ROUTE_PREFIXES = [
  "/api",
  "/auth",
  "/login",
  "/logout",
  "/session",
  "/activate",
  "/forgot-password",
  "/reset-password",
  "/select-organization",
  "/platform/login",
  "/uploads",
  "/documents",
  "/downloads",
];
const STATIC_EXTENSION_PATTERN = /\.(?:css|js|mjs|woff|woff2|ttf|otf)$/i;
const STATIC_HASH_PATTERN = /(?:^|[./_-])[a-f0-9]{8,}(?=[./_-]|$)/i;
const STATIC_DESTINATIONS = new Set(["", "font", "script", "style", "worker"]);

function hasBlockedRoutePrefix(pathname) {
  return BLOCKED_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

function isHashedNextStaticAsset(request, pathname) {
  if (!pathname.startsWith(NEXT_STATIC_PREFIX)) return false;
  if (!STATIC_DESTINATIONS.has(request.destination)) return false;

  const relativePath = pathname.slice(NEXT_STATIC_PREFIX.length);
  return (
    relativePath.length > 0 &&
    !relativePath.includes("..") &&
    STATIC_EXTENSION_PATTERN.test(relativePath) &&
    STATIC_HASH_PATTERN.test(relativePath)
  );
}

function isAllowlistedRequest(request, url) {
  if (request.method !== "GET") return false;
  if (request.mode === "navigate" || request.destination === "document") return false;
  if (url.protocol !== "http:" && url.protocol !== "https:") return false;
  if (url.origin !== self.location.origin || url.search !== "") return false;
  if (url.pathname === "/sw.js" || url.pathname === "/manifest.webmanifest") {
    return false;
  }
  if (hasBlockedRoutePrefix(url.pathname)) return false;
  if (ICON_PATHS.has(url.pathname)) return true;
  return isHashedNextStaticAsset(request, url.pathname);
}

function hasExpectedContentType(url, response) {
  const contentType = (response.headers.get("Content-Type") ?? "")
    .split(";", 1)[0]
    .trim()
    .toLowerCase();

  if (ICON_PATHS.has(url.pathname)) return contentType === "image/png";
  if (/\.css$/i.test(url.pathname)) return contentType === "text/css";
  if (/\.(?:js|mjs)$/i.test(url.pathname)) {
    return [
      "application/javascript",
      "application/x-javascript",
      "text/javascript",
    ].includes(contentType);
  }
  if (/\.(?:woff|woff2|ttf|otf)$/i.test(url.pathname)) {
    return contentType.startsWith("font/") || contentType === "application/font-woff";
  }
  return false;
}

function isCacheableResponse(url, response) {
  if (
    !response.ok ||
    response.status !== 200 ||
    response.type !== "basic" ||
    response.redirected
  ) {
    return false;
  }

  try {
    const responseUrl = new URL(response.url);
    return (
      responseUrl.origin === self.location.origin &&
      responseUrl.pathname === url.pathname &&
      responseUrl.search === url.search &&
      hasExpectedContentType(url, response)
    );
  } catch {
    return false;
  }
}

async function cacheAllowlistedRequest(request, url) {
  let cache = null;
  try {
    cache = await caches.open(CACHE_NAME);
    const cachedResponse = await cache.match(request);
    if (cachedResponse) return cachedResponse;
  } catch {
    cache = null;
  }

  const response = await fetch(request);
  if (cache && isCacheableResponse(url, response)) {
    try {
      await cache.put(request, response.clone());
    } catch {
      return response;
    }
  }
  return response;
}

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting().catch(() => undefined));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      try {
        const cacheNames = await caches.keys();
        await Promise.all(
          cacheNames
            .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
            .map((name) => caches.delete(name)),
        );
      } catch (error) {
        void error;
      }
      await self.clients.claim().catch(() => undefined);
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  let url;
  try {
    url = new URL(event.request.url);
  } catch {
    return;
  }

  if (!isAllowlistedRequest(event.request, url)) return;
  event.respondWith(cacheAllowlistedRequest(event.request, url));
});
