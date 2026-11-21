import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const API = process.env.O2J_API ?? "http://127.0.0.1:8765"

// Built into o2j/static/dist and served by gui.py, so running the app needs only Python.
export default defineConfig({
  base: "/dist/",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: { outDir: "../o2j/static/dist", emptyOutDir: true, chunkSizeWarningLimit: 900 },
  server: {
    proxy: Object.fromEntries(["/api", "/files", "/samples", "/static"].map((p) => [p, API])),
  },
})
