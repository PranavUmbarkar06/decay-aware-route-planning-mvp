import { defineConfig, devices } from "@playwright/test";

// E2E runs against an isolated demo stack (fresh SQLite DB, API + built PWA) started by `python tasks.py e2e`.
// Uses the locally installed Chrome (channel "chrome") with Pixel 7 emulation: a mid-range Android phone.
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: process.env.PHL_BASE ?? "http://localhost:8001", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "pixel7-chrome", use: { ...devices["Pixel 7"], channel: "chrome" } }],
});
