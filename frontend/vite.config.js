import { defineConfig } from "vite";

// Dev proxy: the SPA and API share one origin (localhost:5173),
// which keeps HttpOnly cookies working in development and is the
// same topology nginx uses in production.
export default defineConfig({
    server: {
        proxy: {
            "/api": {
                target: "http://127.0.0.1:8000",
                changeOrigin: true,
            },
            "/uploads": {
                target: "http://127.0.0.1:8000",
                changeOrigin: true,
            },
            "/ws": {
                target: "ws://127.0.0.1:8000",
                ws: true,
            },
        },
    },
});