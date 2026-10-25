import { defineConfig } from "@playwright/test";

// Submission screenshots (not a test gate). `python tasks.py capture`.
export default defineConfig({
  testDir: "./capture",
  timeout: 240_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.PHL_BASE ?? "http://localhost:8001", channel: "chrome", deviceScaleFactor: 2 },
});
