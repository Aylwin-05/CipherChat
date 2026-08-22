import { defineConfig } from "vite";

export default defineConfig({
    server: {
        host: true,
        proxy: {
            "/api": {
                target: "http://127.0.0.1:8000",
                changeOrigin: true,
            },
            "/push": {
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