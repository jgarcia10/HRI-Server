import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "../ui_dist", emptyOutDir: true },
  server: {
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/api": "http://localhost:8000",
      "/stream": "http://localhost:8000",
    },
  },
});
