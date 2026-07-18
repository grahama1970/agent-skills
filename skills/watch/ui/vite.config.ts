import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.WATCH_UI_PORT || 3002),
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.WATCH_API_URL || 'http://127.0.0.1:3003',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
