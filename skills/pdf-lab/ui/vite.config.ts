import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 3012,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:3013',
        changeOrigin: true,
      },
      '/artifacts': {
        target: 'http://127.0.0.1:3013',
        changeOrigin: true,
      },
      '/pdf-lab-api': {
        target: 'http://127.0.0.1:3013',
        changeOrigin: true,
      },
      '/pdf-lab-projects': {
        target: 'http://127.0.0.1:3013',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
