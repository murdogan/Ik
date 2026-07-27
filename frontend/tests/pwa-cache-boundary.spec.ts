import { expect, test } from "@playwright/test";

test("PWA worker never caches authenticated API data", async ({ page }) => {
  const probePath = "/api/v1/p11-pwa-cache-probe";
  let networkRequests = 0;

  await page.route(`**${probePath}`, async (route) => {
    networkRequests += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "Cache-Control": "no-store" },
      body: JSON.stringify({ request: networkRequests }),
    });
  });

  await page.goto("/");
  await page.evaluate(async () => {
    await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
  });
  await page.reload();
  await expect
    .poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller)))
    .toBe(true);

  const responses = await page.evaluate(async (path) => {
    const request = () =>
      fetch(path, {
        credentials: "include",
        headers: { Authorization: "Bearer synthetic-pwa-boundary-token" },
      }).then((response) => response.json());
    return [await request(), await request()];
  }, probePath);

  expect(responses).toEqual([{ request: 1 }, { request: 2 }]);
  expect(networkRequests).toBe(2);

  const cachedUrls = await page.evaluate(async () => {
    const urls: string[] = [];
    for (const cacheName of await caches.keys()) {
      const cache = await caches.open(cacheName);
      urls.push(...(await cache.keys()).map((request) => request.url));
    }
    return urls;
  });
  expect(cachedUrls.some((url) => new URL(url).pathname === probePath)).toBe(
    false,
  );

  const worker = await page.request.get("/sw.js");
  expect(worker.status()).toBe(200);
  expect(worker.headers()["cache-control"]).toContain("no-store");
  expect(worker.headers()["service-worker-allowed"]).toBe("/");
});
