import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // REST API
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
      // WebSocket
      '/ws': {
        target: 'ws://127.0.0.1:8080',
        ws: true,
        changeOrigin: true,
      },
      // Static files (SVG agents)
      '/static': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    }
  },
  build: {
    outDir: '../static_build',
    emptyOutDir: true,
  }
})
