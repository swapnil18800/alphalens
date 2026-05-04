import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    strictPort: true,
    proxy: {
      // NOTE: use 127.0.0.1 not localhost — on Windows, localhost resolves to ::1 (IPv6)
      // which the uvicorn server does NOT listen on (it binds 127.0.0.1 only).
      // Also: /chat is a React Router route — do NOT proxy it or direct-URL reloads break.
      '/api':       { target: 'http://127.0.0.1:8000', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') },
      '/sessions':  { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health':    { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws':        { target: 'ws://127.0.0.1:8000',   ws: true, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
