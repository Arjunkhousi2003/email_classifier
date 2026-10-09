import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/fetch-emails": "http://localhost:8000",
      "/filter-emails": "http://localhost:8000",
      "/emails": "http://localhost:8000",
      "/get-categories": "http://localhost:8000",
      "/rules": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
