import { test, expect } from "@playwright/test";

test("welcome and demo keymap work without hardware", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Make every key/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Explore demo", exact: true }).click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("DEMO MODE");
  const cap = page.locator('[data-key="0:0"]');
  await expect(cap).toHaveText("Esc");
  await cap.click();
  await page.getByRole("searchbox").fill("KC_A");
  await page
    .locator(".keycode-picker button")
    .filter({ hasText: /^A$/ })
    .click();
  await expect(cap).toHaveText("A");
  await page
    .getByRole("button", { name: "Matrix tester", exact: true })
    .click();
  await expect(page.locator(".matrix-cell")).toHaveCount(96);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Make every key/ }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("layout is responsive on small and large displays", async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 950 },
    { width: 720, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: "Connect your keyboard" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBeTruthy();
  }
});

test("connecting requires WebHID and never invokes a desktop helper", async ({
  page,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(navigator, "hid", {
      value: undefined,
      configurable: true,
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Connect your keyboard" }).click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("WebHID is unavailable");
});
