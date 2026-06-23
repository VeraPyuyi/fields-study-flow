import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../fields_study_flow/frontend_dist",
    emptyOutDir: true,
    manifest: "manifest.json",
    rollupOptions: {
      input: "index.html",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
