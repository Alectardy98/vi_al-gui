// Serve only dist/ beneath a project path, as GitHub Pages does.
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import assert from "node:assert/strict";
import { chromium } from "@playwright/test";
import { mockKeyboard } from "../tests/browser/mock-hid.js";

const root = resolve("dist"),
  prefix = "/vi_al-gui/";
const types = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".wasm": "application/wasm",
};
const server = createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(
      new URL(req.url, "http://localhost").pathname,
    );
    if (!pathname.startsWith(prefix)) throw Error("Outside site");
    const path = resolve(root, pathname.slice(prefix.length) || "index.html");
    if (!path.startsWith(root + sep)) throw Error("Outside dist");
    const data = await readFile(path);
    res.writeHead(200, {
      "Content-Type": types[extname(path)] || "application/octet-stream",
    });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch(
    process.env.CI
      ? {}
      : {
          executablePath: process.env.CHROME_BIN || "/opt/google/chrome/chrome",
          args: ["--no-sandbox"],
        },
  );
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [],
    requests = [];
  context.on("page", (page) => {
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("response", (response) => {
      if (response.status() >= 400)
        errors.push(`${response.status()} ${response.url()}`);
    });
    page.on("request", (req) => requests.push(req.url()));
  });
  const screenshots = process.env.WEB_SCREENSHOTS;
  if (screenshots) await mkdir(screenshots, { recursive: true });
  const shot = async (page, name) => {
    if (screenshots)
      await page.screenshot({
        path: resolve(screenshots, `${name}.png`),
        fullPage: true,
      });
  };
  const welcome = await context.newPage();
  await welcome.goto(origin + prefix);
  await welcome.getByRole("heading", { name: /Make every key/ }).waitFor();
  await shot(welcome, "welcome");
  await welcome
    .getByRole("button", { name: "Explore demo", exact: true })
    .click();
  await welcome.locator('[data-key="0:0"]').waitFor();
  await shot(welcome, "demo");
  await welcome.close();
  for (const [kind, tab] of [
    ["my2k", "Auxiliary Display"],
    ["ec", "Actuation"],
    ["aw", "AW768 lighting"],
    ["xwhatsit", "Calibration"],
  ]) {
    const page = await context.newPage();
    await mockKeyboard(page, kind);
    await page.goto(origin + prefix);
    await page.getByRole("button", { name: "Connect your keyboard" }).click();
    await page.locator(".keycap").first().waitFor();
    await page.getByRole("button", { name: tab, exact: true }).click();
    if (kind === "my2k")
      await page.getByRole("textbox", { name: "Typing label" }).waitFor();
    if (kind === "ec")
      await page
        .getByRole("slider", { name: "Global default", exact: true })
        .waitFor();
    if (kind === "xwhatsit")
      await page
        .getByRole("slider", { name: "Threshold margin", exact: true })
        .waitFor();
    if (kind === "aw") {
      await page
        .getByRole("button", { name: "Connect lighting PCB", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Save changes to keyboard", exact: true })
        .waitFor();
    }
    await shot(page, kind);
    await page.close();
  }
  assert.deepEqual(errors, []);
  assert.equal(
    requests.every(
      (url) =>
        url.startsWith(origin + prefix) ||
        url.startsWith("data:") ||
        url.startsWith("blob:"),
    ),
    true,
    "Unexpected external request",
  );
  console.log(
    "Production build passed: project subpath, demo, all four bundled providers, XZ decoding, no external requests or page errors. Simulated USB only.",
  );
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
