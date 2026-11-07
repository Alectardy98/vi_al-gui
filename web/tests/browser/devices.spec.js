import { test, expect } from "@playwright/test";
import { fixture, mockKeyboard } from "./mock-hid.js";
import { readFileSync } from "node:fs";
import { parseCrs } from "../../../addons/my2k/web/files.js";

async function connect(page, kind) {
  await mockKeyboard(page, kind);
  await page.goto("/");
  await page.getByRole("button", { name: "Connect your keyboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Keymap", exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Connected");
}
test("Pro X connects using its actual firmware definition and identity", async ({
  page,
}) => {
  await connect(page, "prox");
  await expect(page.locator(".device-info")).toContainText(
    "EC Pro X ANSI/ISO - Alectardy98",
  );
  await expect(page.locator(".keycap")).toHaveCount(60);
  await expect(
    page.getByRole("button", { name: "Actuation", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Animations", exact: true }),
  ).toHaveCount(0);
});
test("corrupt definition reports competing configurators and closes the failed connection", async ({
  page,
}) => {
  await mockKeyboard(page, "prox");
  await page.addInitScript(() => {
    window.__corruptDefinition = true;
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Connect your keyboard", exact: true })
    .click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Close desktop Vi_al");
  await expect(
    page.getByRole("button", { name: "Actuation", exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(() =>
      window.__hidWrites.every((q) => [1, 254].includes(q[0])),
    ),
  ).toBeTruthy();
});
test("browser GIF conversion preserves source delays and produces native 128×128 RGB565", async ({
  page,
}) => {
  await connect(page, "my2k");
  await page.getByRole("button", { name: "Animations", exact: true }).click();
  await page.getByLabel("Select GIF or CRS", { exact: true }).setInputFiles({
    name: "two-frames.gif",
    mimeType: "image/gif",
    buffer: Buffer.from(fixture.gif, "base64"),
  });
  const received = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Convert and save to desktop", exact: true })
    .click();
  const file = await received,
    data = new Uint8Array(readFileSync(await file.path())),
    movie = parseCrs(data);
  expect(movie.frames).toBe(2);
  expect(movie.delays).toEqual([50, 100]);
  expect([...data.slice(movie.offset, movie.offset + 2)]).toEqual([0xf8, 0]);
  expect([...data.slice(movie.offset + 32768, movie.offset + 32770)]).toEqual([
    0, 0x1f,
  ]);
  expect(
    await page.evaluate(
      () =>
        window.__hidWrites.filter(
          (q) => q[0] === 253 && q[1] === 238 && [3, 4, 5].includes(q[2]),
        ).length,
    ),
  ).toBe(0);
});
test("generic Vial macros, dynamic actions and QMK settings save and read back", async ({
  page,
}) => {
  await connect(page, "core");
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Macro action 1" }),
  ).toHaveValue("Hello");
  await page
    .getByRole("textbox", { name: "Macro action 1" })
    .fill("Browser macro");
  await page.getByRole("button", { name: "Save macro", exact: true }).click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Saved and verified");
  await page
    .getByRole("button", { name: "Tap Dance & more", exact: true })
    .click();
  await expect(
    page.getByLabel("Tapping term · ms", { exact: true }),
  ).toHaveValue("200");
  await page.getByLabel("Tapping term · ms", { exact: true }).fill("250");
  await page.getByRole("button", { name: "Save entry", exact: true }).click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Saved and verified");
  await page.getByRole("button", { name: "QMK settings", exact: true }).click();
  await page
    .getByRole("spinbutton", { name: "Tapping Term", exact: true })
    .fill("230");
  await page
    .getByRole("checkbox", { name: "Enable N-key rollover", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Apply QMK settings", exact: true })
    .click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Saved and verified");
  expect(await page.evaluate(() => window.__qmkValues)).toEqual({
    7: 230,
    21: 32896,
  });
});
test("AW768 connects its separate lighting PCB and performs the native persistent save", async ({
  page,
}) => {
  await connect(page, "aw");
  await expect(
    page.getByRole("button", { name: "Animations", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "AW768 lighting", exact: true })
    .click();
  expect(await page.evaluate(() => window.__awWrites.length)).toBe(0);
  await page
    .getByRole("button", { name: "Connect lighting PCB", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Save changes to keyboard", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Select all groups", exact: true })
    .click();
  await page.getByLabel("Effect", { exact: true }).selectOption("0");
  await page.locator("input[type=color]").fill("#ff0000");
  await page
    .getByRole("button", { name: "Save changes to keyboard", exact: true })
    .click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Native save sequence completed");
  const frames = await page.evaluate(() =>
    window.__awWrites.filter((r) => r[0] === "output").map((r) => r[1]),
  );
  expect(frames).toHaveLength(16);
  expect(
    frames
      .slice(0, 8)
      .every(
        (r) =>
          r[2] === 0 && r[12] === 1 && r[3] === 255 && r[4] === 0 && r[5] === 0,
      ),
  ).toBeTruthy();
  expect(
    frames.slice(8).every((r) => r[2] === 255 && r[12] === 2),
  ).toBeTruthy();
});
test("real XZ definition decoding and HID keymap read/write/readback", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await connect(page, "my2k");
  await page.locator('[data-key="0:0"]').click();
  await page.getByRole("searchbox").fill("KC_Z");
  await page
    .locator(".keycode-picker button")
    .filter({ hasText: /^Z$/ })
    .click();
  await expect(page.locator('[data-key="0:0"]')).toHaveText("Z");
  const writes = await page.evaluate(() =>
    window.__hidWrites.filter((q) => q[0] === 5),
  );
  expect(writes).toHaveLength(1);
  expect(writes[0].slice(0, 6)).toEqual([5, 0, 0, 0, 0, 29]);
  expect(errors).toEqual([]);
});
test("MY-2K pages read current configuration without unsolicited setting writes", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await connect(page, "my2k");
  for (const title of [
    "RGB Strips",
    "RGB Grid",
    "Lock Lights",
    "Touch bar",
    "Gaming",
    "General",
    "Auxiliary Display",
    "Animations",
  ]) {
    await page.getByRole("button", { name: title, exact: true }).click();
    await expect(page.locator(".page-body")).not.toBeEmpty();
    await expect(page.locator(".page-body > .notice.error")).toHaveCount(0);
  }
  const mutations = await page.evaluate(() =>
    window.__hidWrites.filter(
      (q) =>
        q[0] === 253 &&
        (([235, 231, 233].includes(q[1]) && [2, 3, 4].includes(q[2])) ||
          (q[1] === 232 && [2, 3, 4, 7].includes(q[2])) ||
          (q[1] === 230 && q[2] === 6) ||
          [62, 32, 68, 76].includes(q[1])),
    ),
  );
  expect(mutations).toEqual([]);
  expect(errors).toEqual([]);
});
test("touch apply uses the existing CRC, revision, acknowledgement and readback workflow", async ({
  page,
}) => {
  await connect(page, "my2k");
  await page.getByRole("button", { name: "Touch bar", exact: true }).click();
  const slider = page.getByRole("slider", { name: "Sensitivity", exact: true });
  await expect(slider).toHaveValue("67");
  await slider.fill("83");
  await page.getByRole("button", { name: "Apply touch settings" }).click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Saved and verified");
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await page.getByRole("button", { name: "Touch bar", exact: true }).click();
  await expect(
    page.getByRole("slider", { name: "Sensitivity", exact: true }),
  ).toHaveValue("83");
});
test("OLED editing is local until Apply and Happy/Clock are exclusive", async ({
  page,
}) => {
  await connect(page, "my2k");
  await page
    .getByRole("button", { name: "Auxiliary Display", exact: true })
    .click();
  await expect(page.getByRole("textbox", { name: "Idle message" })).toHaveValue(
    "Hello Vi_al",
  );
  await page.getByLabel("Font", { exact: true }).selectOption("monospace");
  await page
    .getByRole("textbox", { name: "Idle message" })
    .fill("Browser hello");
  await page.getByRole("textbox", { name: "Typing label" }).fill("WEB");
  await page.getByLabel("Screen Saver mode").selectOption("1");
  expect(
    await page.evaluate(
      () =>
        window.__hidWrites.filter(
          (q) => q[0] === 253 && q[1] === 232 && [2, 3, 4].includes(q[2]),
        ).length,
    ),
  ).toBe(0);
  await page
    .getByRole("button", { name: "Apply changes", exact: true })
    .click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("persisted and read back");
  await page.getByRole("button", { name: "Reload from keyboard" }).click();
  await expect(page.getByRole("textbox", { name: "Idle message" })).toHaveValue(
    "Browser hello",
  );
  await expect(page.getByRole("textbox", { name: "Typing label" })).toHaveValue(
    "WEB",
  );
  await expect(page.getByLabel("Screen Saver mode")).toHaveValue("1");
});
test("clock-on-connect is opt-in, stores only a browser preference, and uses ISO weekdays", async ({
  page,
}) => {
  await connect(page, "my2k");
  await page
    .getByRole("button", { name: "Auxiliary Display", exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: "Sync date & time on connect", exact: true })
    .check();
  expect(
    await page.evaluate(
      () =>
        window.__hidWrites.filter(
          (q) => q[0] === 253 && q[1] === 232 && q[2] === 7,
        ).length,
    ),
  ).toBe(0);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await page.getByRole("button", { name: "Connect your keyboard" }).click();
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Connected");
  const packets = await page.evaluate(() =>
    window.__hidWrites.filter(
      (q) => q[0] === 253 && q[1] === 232 && q[2] === 7,
    ),
  );
  expect(packets).toHaveLength(1);
  expect(packets[0][7]).toBeGreaterThanOrEqual(1);
  expect(packets[0][7]).toBeLessThanOrEqual(7);
});
test("EC42 pages and atomic global/per-key actuation preserve the protocol", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await connect(page, "ec");
  await expect(
    page.getByRole("button", { name: "Animations", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Actuation", exact: true }).click();
  const global = page.getByRole("slider", {
    name: "Global default",
    exact: true,
  });
  await expect(global).toHaveValue("54");
  await page.locator('[data-key="0:0"]').click();
  await expect(
    page.getByRole("slider", { name: "Per-key actuation", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("slider", { name: "Per-key actuation", exact: true })
    .fill("61");
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("Per-key actuation saved");
  await global.fill("45");
  await expect(
    page.getByRole("status", { name: "Keyboard status" }),
  ).toContainText("all per-key overrides cleared");
  await expect(
    page.getByRole("slider", { name: "Per-key actuation", exact: true }),
  ).toHaveValue("45");
  await page.getByRole("button", { name: "Live sensors", exact: true }).click();
  await expect(page.locator(".matrix-cell")).toHaveCount(96);
  await page.evaluate(() => {
    window.__ecPress = true;
  });
  await expect(page.locator(".matrix-cell.pressed")).toHaveCount(1);
  await page.getByRole("button", { name: "Calibration", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Start manual calibration" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
