import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// El front llama a /api/... y Vite lo reenvía a la API local (python -m delivery_crew.api).
// Así no hay problemas de CORS en desarrollo.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.API_URL ?? "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
