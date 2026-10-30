import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    proxy: { "/api": API, "/tiles": API, "/geo": API },
  },
});
