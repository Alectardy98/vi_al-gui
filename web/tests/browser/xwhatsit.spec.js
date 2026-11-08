import { test, expect } from "@playwright/test";
import { mockKeyboard } from "./mock-hid.js";
async function connect(page, legacy = false) {
  await mockKeyboard(page, "xwhatsit");
  if (legacy) await page.addInitScript(() => (window.__xwLegacy = true));
  await page.goto("/");
  await page.getByRole("button", { name: "Connect your keyboard" }).click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Connected");
}
test("xwhatsit uses firmware layout, live saves/readback, defaults, and follows held sensor", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await connect(page);
  await expect(page.locator(".keycap")).toHaveCount(50);
  await page.getByRole("button", { name: "Calibration", exact: true }).click();
  const margin = page.getByRole("slider", {
    name: "Threshold margin",
    exact: true,
  });
  await expect(margin).toBeEnabled();
  await expect(
    page.getByText(/56 \/ 56 calibration positions sampled/),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        window.__hidWrites.filter(
          (q) => q[0] === 85 && [50, 51, 24, 18].includes(q[2]),
        ).length,
    ),
  ).toBe(0);
  await margin.fill("100");
  await margin.dispatchEvent("change");
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("saved and verified");
  expect(await page.evaluate(() => window.__xwSettings[5])).toBe(100);
  await page
    .getByRole("button", { name: "Restore calibration defaults" })
    .click();
  await expect(margin).toHaveValue("96");
  await expect(
    page.getByRole("button", { name: "Recalibrate now" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Live sensors", exact: true }).click();
  await page.evaluate(() => (window.__xwPressed = true));
  await expect(page.getByText(/Signal 900.*Held/)).toBeVisible();
  await expect(page.locator(".matrix-cell.pressed")).toHaveCount(1);
  await page.evaluate(() => (window.__xwPressed = false));
  await expect(page.getByText(/Signal 500.*Released/)).toBeVisible();
  await page.getByRole("button", { name: "General", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Bootloader", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("legacy utility firmware can monitor without exposing unsupported writes", async ({
  page,
}) => {
  await connect(page, true);
  await page.getByRole("button", { name: "Calibration", exact: true }).click();
  await expect(
    page.getByRole("slider", { name: "Threshold margin", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Restore calibration defaults" }),
  ).toBeDisabled();
  await expect(
    page.getByText(/Monitoring works with this firmware/),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => window.__hidWrites.filter((q) => q[0] === 85 && q[2] >= 48).length,
    ),
  ).toBe(0);
});
