import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const watchApiTarget =
  process.env.VITE_WATCH_API_TARGET ||
  'http://127.0.0.1:3003'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3002,
    strictPort: true,
    proxy: {
      '/api': {
        target: watchApiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
