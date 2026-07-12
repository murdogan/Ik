import { expect, test, type Route } from "@playwright/test";

function dataEnvelope(data: unknown): string {
  return JSON.stringify({ data });
}

function errorEnvelope(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: "browser-recovery",
    },
  });
}

test("login offers a non-enumerating password reset request", async ({ page }) => {
  const email = "unknown-or-known@wealthyfalcon.demo";
  let requestCount = 0;

  await page.route("**/api/v1/auth/password-reset/request", async (route: Route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toEqual({ email });
    requestCount += 1;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: dataEnvelope({ status: "accepted" }),
    });
  });

  await page.goto("/login");
  await page.getByRole("link", { name: "Parolanızı mı unuttunuz?" }).click();
  await expect(page).toHaveURL(/\/forgot-password$/);
  await page.getByLabel("E-posta adresi").fill(email);
  await page.getByRole("button", { name: "Yenileme bağlantısı iste" }).click();

  await expect(page.getByText("İsteğiniz alındı", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Bu e-posta adresiyle eşleşen bir hesap varsa", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText(email)).toHaveCount(0);
  expect(requestCount).toBe(1);
});

test("reset reads and scrubs a fragment token before setting a new password", async ({
  page,
}) => {
  const token = "safe-browser-password-reset-token";
  const password = "A safe recovered account password";
  let confirmCount = 0;

  await page.route("**/api/v1/auth/password-reset/confirm", async (route: Route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toEqual({ token, password });
    confirmCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: dataEnvelope({ status: "completed" }),
    });
  });

  await page.goto(`/reset-password#token=${token}`);
  await expect(page).toHaveURL(/\/reset-password$/);
  expect(await page.evaluate(() => window.location.hash)).toBe("");
  expect(await page.evaluate(() => window.history.state?.token)).toBeUndefined();

  await page.getByLabel("Yeni parola", { exact: true }).fill(password);
  await page.getByLabel("Yeni parolayı doğrulayın").fill(`${password}!`);
  await page.getByRole("button", { name: "Parolamı yenile" }).click();
  await expect(page.getByText("Parola alanları eşleşmiyor")).toBeVisible();
  expect(confirmCount).toBe(0);

  await page.getByLabel("Yeni parolayı doğrulayın").fill(password);
  await page.getByRole("button", { name: "Parolamı yenile" }).click();
  await expect(page.getByText("Parolanız yenilendi", { exact: true })).toBeVisible();
  expect(confirmCount).toBe(1);

  const browserStorage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
      history: window.history.state,
    }),
  );
  expect(browserStorage).not.toContain(token);
});

test("an invalid reset credential offers a new generic request", async ({ page }) => {
  await page.route("**/api/v1/auth/password-reset/confirm", async (route: Route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: errorEnvelope("password_reset_invalid"),
    });
  });

  await page.goto("/reset-password#token=expired-browser-token");
  await page.getByLabel("Yeni parola", { exact: true }).fill("A replacement password value");
  await page
    .getByLabel("Yeni parolayı doğrulayın")
    .fill("A replacement password value");
  await page.getByRole("button", { name: "Parolamı yenile" }).click();

  await expect(
    page.getByText("geçersiz, süresi dolmuş veya daha önce kullanılmış", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Yeni bağlantı iste" })).toHaveAttribute(
    "href",
    "/forgot-password",
  );
  await expect(page.getByText("browser-recovery")).toBeVisible();
});

test("reset credentials are accepted only from the URL fragment", async ({ page }) => {
  await page.goto("/reset-password?token=query-string-token-must-not-be-used");

  await expect(page.getByText("Yenileme bağlantısı bulunamadı")).toBeVisible();
  await expect(page.getByRole("button", { name: "Parolamı yenile" })).toHaveCount(0);
});
