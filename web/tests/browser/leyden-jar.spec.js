import { test, expect } from "@playwright/test";
import { mockLeyden } from "./leyden-mock.js";
async function connect(page, kind = "fat", legacy = false, options = {}) {
  await mockLeyden(page, kind, legacy, options);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Connect keyboard", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Calibration", exact: true }),
  ).toBeVisible();
}
const edits = () =>
  window.__hidWrites.filter(
    (q) =>
      q[0] === 3 && [0x83, 0x85, 0x89, 0x8a, 0x8b, 0x93, 0x94].includes(q[1]),
  );
test("calibration renders device geometry, live values and all groups; edits require Apply", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await connect(page);
  await page.getByRole("button", { name: "Calibration", exact: true }).click();
  await expect(
    page.getByRole("slider", { name: "Group trigger", exact: true }),
  ).toBeEnabled();
  await expect(page.locator(".leyden-calibration tbody tr")).toHaveCount(2);
  await expect(
    page.locator(".leyden-keyboard .keycap").first().locator(".keycap-label"),
  ).not.toHaveText("—");
  const bounds = await page
    .locator(".leyden-calibration table")
    .evaluate((t) => ({
      table: t.getBoundingClientRect().right,
      card: t.parentElement.getBoundingClientRect().right,
    }));
  expect(bounds.table).toBeLessThanOrEqual(bounds.card);
  expect(await page.evaluate(edits)).toHaveLength(0);
  const trigger = page.getByRole("slider", {
    name: "Group trigger",
    exact: true,
  });
  await trigger.fill("440");
  await trigger.dispatchEvent("input");
  expect(await page.evaluate(edits)).toHaveLength(0);
  await page
    .getByRole("button", { name: "Apply and save", exact: true })
    .click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("verified by readback");
  expect(
    await page.evaluate(() => window.__leydenPeer.saved.some(Boolean)),
  ).toBe(true);
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Restore calibration defaults" })
    .click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("keymaps preserved");
  expect(
    await page.evaluate(() => window.__leydenPeer.saved.some(Boolean)),
  ).toBe(false);
  expect(errors).toEqual([]);
});
test("live sensor keys show matrix coordinates, follow presses and stop on navigation", async ({
  page,
}) => {
  await connect(page, "beamal");
  await page.getByRole("button", { name: "Live sensors", exact: true }).click();
  await page.evaluate(() => window.__leydenPeer.pressed.add("4:2"));
  await expect(page.locator(".leyden-reading")).toContainText("QMK 4, 9");
  await expect(page.locator('.leyden-keyboard [data-key="4:9"]')).toHaveClass(
    /pressed/,
  );
  await expect(
    page.locator('.leyden-keyboard [data-key="4:9"] .keycap-label'),
  ).toContainText("4,9");
  await page
    .getByRole("button", { name: "Controller matrix", exact: true })
    .click();
  await expect(page.locator(".leyden-matrix button")).toHaveCount(144);
  await page.evaluate(() => window.__leydenPeer.pressed.clear());
  await expect(page.locator(".leyden-reading")).toContainText("Released");
  await page.getByRole("button", { name: "Controller", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Disable typing", exact: true }),
  ).toBeVisible();
  const count = await page.evaluate(
    () => window.__hidWrites.filter((q) => q[1] === 0x84).length,
  );
  await page.waitForTimeout(700);
  expect(
    await page.evaluate(
      () => window.__hidWrites.filter((q) => q[1] === 0x84).length,
    ),
  ).toBe(count);
  expect(await page.evaluate(edits)).toHaveLength(0);
});
test("legacy firmware advertises RAM-only controls and unsupported defaults stay disabled", async ({
  page,
}) => {
  await connect(page, "fat", true);
  await page.getByRole("button", { name: "Calibration", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Apply to this group", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Restore calibration defaults" }),
  ).toBeDisabled();
  await expect(
    page.getByText(/Legacy firmware: trigger changes/),
  ).toBeVisible();
});
test("3178 blue switch stays digital, not an invented analog graph", async ({
  page,
}) => {
  await connect(page, "direct");
  await page.getByRole("button", { name: "Live sensors", exact: true }).click();
  await page.evaluate(() => (window.__leydenPeer.directPressed = true));
  await expect(page.locator(".leyden-reading")).toContainText("Digital switch");
  await expect(page.locator('.leyden-keyboard [data-key="8:12"]')).toHaveClass(
    /pressed/,
  );
});
test("modified 3276 supports four by twenty controller view and responsive controls", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await connect(page, "expanded");
  await page.getByRole("button", { name: "Live sensors", exact: true }).click();
  await page
    .getByRole("button", { name: "Controller matrix", exact: true })
    .click();
  await expect(page.locator(".leyden-matrix button")).toHaveCount(80);
  await page.getByRole("button", { name: "Controller", exact: true }).click();
  await page
    .getByRole("button", { name: "Disable typing", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Enable typing", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Enable typing", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Disable typing", exact: true }),
  ).toBeVisible();
});

test("all sixteen groups remain visible without an inner vertical scrollbar", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1100, height: 850 });
  await connect(page, "fat", false, { bins: 16 });
  await page.getByRole("button", { name: "Calibration", exact: true }).click();
  await expect(page.locator(".leyden-calibration tbody tr")).toHaveCount(16);
  await page.getByRole("button", { name: "Group 16", exact: true }).click();
  await expect(
    page.getByRole("spinbutton", { name: "Group trigger value" }),
  ).toHaveValue("570");
  const inner = await page
    .locator(".leyden-calibration table")
    .evaluate(
      (table) =>
        table.parentElement.scrollHeight <=
        table.parentElement.clientHeight + 1,
    );
  expect(inner).toBe(true);
});
