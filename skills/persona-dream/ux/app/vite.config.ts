import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI service (ux/server.py) owns every route under /api. Proxying
// them keeps the dev server same-origin, so audio <audio src> and fetch behave
// in dev exactly as they do from the built bundle it serves at /.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8790', changeOrigin: true } },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
