import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// During development, requests to /api and /ws are passed on to the backend (port 8000 by default),
// so the frontend never needs to know the backend's address. SM_API_TARGET points a test copy elsewhere.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {}
const API = env.SM_API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': API,
      '/ws': { target: API.replace(/^http/, 'ws'), ws: true },
    },
  },
})
