import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 把 /api 與 /files 代理到 FastAPI 後端，前端開發時免處理 CORS
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/files": "http://localhost:8000",
    },
  },
});
