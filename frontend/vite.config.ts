/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

const API = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.PHL_API ?? "http://localhost:8000";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["logo-placeholder.svg", "icons/icon-192.png", "icons/icon-512.png"],
      manifest: {
        name: "Impact Tank Post-Harvest Platform (working title)",
        short_name: "PHL Platform",
        description: "Traceability, wastage logging, shelf-life triage and quality-aware routing for fresh produce (prototype).",
        theme_color: "#0f8b8d",
        background_color: "#f7f8f7",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // App shell + static geo layers work offline; API writes go through the IndexedDB sync queue instead.
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        navigateFallbackDenylist: [/^\/api/, /^\/reports/],
        runtimeCaching: [
          { urlPattern: /\/geo\/.*\.geojson$/, handler: "CacheFirst", options: { cacheName: "geo" } },
          { urlPattern: /\/api\/v1\/(meta|roles|nodes|wastage\/reasons)/, handler: "NetworkFirst", options: { cacheName: "api-ref" } },
          { urlPattern: /^https:\/\/tile\.openstreetmap\.org\/.*/, handler: "CacheFirst",
            options: { cacheName: "tiles", expiration: { maxEntries: 400, maxAgeSeconds: 7 * 24 * 3600 } } },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: { "/api": API, "/geo": API, "/reports": API, "/healthz": API },
  },
  build: { chunkSizeWarningLimit: 1500, sourcemap: false },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], include: ["src/**/*.test.{ts,tsx}"] },
});
