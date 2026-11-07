import { test, expect } from "@playwright/test";
import { mockKeyboard } from "./mock-hid.js";

async function connect(page, kind = "zenithal") {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await mockKeyboard(page, kind);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Connect your keyboard", exact: true })
    .click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Connected");
}
test("Zenithal spacebar, bottom numpad and keycode controls stay within the compact layout", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await connect(page);
  await expect(page.locator(".keycap")).toHaveCount(84);
  const space = page.locator('[data-key="8:3"]'),
    numpad = page.locator('[data-key="8:7"]');
  await expect(space).toHaveText("Space");
  await expect(space).toBeInViewport();
  await expect(numpad).toBeInViewport();
  const board = await page.locator(".keyboard").boundingBox();
  expect(board.height).toBeLessThan(300);
  await expect(
    page.getByRole("heading", { name: "Keycodes", exact: true }),
  ).toBeInViewport();
  expect(
    await page
      .locator(".keyboard-scroll")
      .evaluate((node) => node.scrollWidth <= node.clientWidth + 1),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});
test("Zenithal alternate layouts preview locally, keep ISO shape and persist only on Apply", async ({
  page,
}) => {
  await connect(page);
  await page.getByRole("button", { name: "Layout", exact: true }).click();
  await page.getByLabel("ISO Enter", { exact: true }).selectOption("1");
  await page.getByLabel("Bottom Row", { exact: true }).selectOption("12");
  await page.getByLabel("Numpad Plus", { exact: true }).selectOption("2");
  await expect(page.locator('[data-key="8:3"]')).toBeVisible();
  expect((await page.locator(".keyboard").boundingBox()).height).toBeLessThan(
    300,
  );
  expect(
    await page
      .locator('[data-key="2:7"]')
      .evaluate((node) => getComputedStyle(node).clipPath),
  ).toContain("polygon");
  expect(
    await page.evaluate(
      () => window.__hidWrites.filter((q) => q[0] === 3).length,
    ),
  ).toBe(0);
  await page.getByRole("button", { name: "Apply layout", exact: true }).click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Layout saved and verified");
  await expect(page.getByLabel("Bottom Row", { exact: true })).toHaveValue(
    "12",
  );
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await expect(page.locator('[data-key="8:3"]')).toBeInViewport();
  expect(
    await page.evaluate(
      () => window.__hidWrites.filter((q) => q[0] === 3).length,
    ),
  ).toBe(1);
});
test("all picker tabs are present and custom User actions use definition identities with readback", async ({
  page,
}) => {
  await connect(page, "zenithal_alec");
  for (const name of [
    "Basic",
    "ISO/JIS",
    "Layers",
    "Quantum",
    "Backlight",
    "Media & Mouse",
    "MIDI",
    "Tap Dance",
    "User",
    "Macro",
    "Any",
  ])
    await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "All", exact: true }).click();
  expect(await page.locator(".keycode-picker button").count()).toBeGreaterThan(
    120,
  );
  await page.getByRole("tab", { name: "User", exact: true }).click();
  await expect(page.locator(".keycode-picker button")).toHaveCount(39);
  expect(
    await page.evaluate(
      () => window.__hidWrites.filter((q) => q[0] === 5).length,
    ),
  ).toBe(0);
  await page.locator('[data-key="0:0"]').click();
  const thumb = page.locator('[data-keycode="USER38"]');
  await expect(thumb).toHaveText("THUM");
  await thumb.focus();
  await expect(page.locator(".keycode-description")).toContainText(
    ":thumbsup:",
  );
  await thumb.click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("saved and read back");
  await expect(page.locator('[data-key="0:0"]')).toHaveText("THUM");
  expect(
    await page.evaluate(() =>
      window.__hidWrites
        .filter((q) => q[0] === 5)
        .at(-1)
        .slice(0, 6),
    ),
  ).toEqual([5, 0, 0, 0, 0x7e, 38]);
  await page.getByRole("searchbox").fill("Virtual Desktop Right");
  await expect(page.locator('[data-keycode="USER01"]')).toHaveText("VDRT");
});
test("combination picker waits for the inner key and Any expressions retain wire encoding", async ({
  page,
}) => {
  await connect(page);
  await page.locator('[data-key="0:0"]').click();
  await page.getByRole("tab", { name: "Quantum", exact: true }).click();
  await page.locator('[data-keycode="LCTL_T(kc)"]').click();
  expect(
    await page.evaluate(
      () => window.__hidWrites.filter((q) => q[0] === 5).length,
    ),
  ).toBe(0);
  await page.locator('[data-keycode="KC_A"]').click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("saved and read back");
  expect(
    await page.evaluate(() =>
      window.__hidWrites
        .filter((q) => q[0] === 5)
        .at(-1)
        .slice(4, 6),
    ),
  ).toEqual([0x21, 4]);
  await page.getByRole("tab", { name: "Layers", exact: true }).click();
  await page.locator('[data-keycode="LT3(kc)"]').click();
  await page.locator('[data-keycode="KC_SPACE"]').click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("saved and read back");
  expect(
    await page.evaluate(() =>
      window.__hidWrites
        .filter((q) => q[0] === 5)
        .at(-1)
        .slice(4, 6),
    ),
  ).toEqual([0x43, 44]);
  await page.getByRole("tab", { name: "Any", exact: true }).click();
  await page.getByRole("textbox", { name: "Any keycode" }).fill("LCTL(KC_A)");
  await page
    .getByRole("button", { name: "Assign keycode", exact: true })
    .click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("saved and read back");
  expect(
    await page.evaluate(() =>
      window.__hidWrites
        .filter((q) => q[0] === 5)
        .at(-1)
        .slice(4, 6),
    ),
  ).toEqual([1, 4]);
});
