import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// build directo a webui_dist: es lo que sirve `wyss web` (src/bootstrap/web.py)
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../src/bootstrap/webui_dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:7777',
    },
  },
})
