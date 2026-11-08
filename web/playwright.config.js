import { defineConfig } from "@playwright/test";
const port = Number(process.env.WEB_TEST_PORT || 5173);
export default defineConfig({
  testDir: "./tests/browser",
  timeout: 30000,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    launchOptions: process.env.CI
      ? {}
      : {
          executablePath: process.env.CHROME_BIN || "/opt/google/chrome/chrome",
          args: ["--no-sandbox"],
        },
  },
  webServer: {
    command: `npm run dev -- --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: !process.env.CI,
  },
});
