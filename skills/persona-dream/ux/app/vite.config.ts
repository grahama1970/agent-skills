import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The #dream route imports the pipeline workspace from the skill's ui/src,
// two levels above this app root, so widen fs.allow to the skill root.
const skillRoot = fileURLToPath(new URL('../..', import.meta.url))

// The FastAPI service (ux/server.py) owns every route under /api. Proxying
// them keeps the dev server same-origin, so audio <audio src> and fetch behave
// in dev exactly as they do from the built bundle it serves at /.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    fs: { allow: [skillRoot] },
    proxy: {
      // Order matters: first match wins, so specific prefixes must precede /api.
      '/api/projects/dream': { target: 'http://127.0.0.1:8791', changeOrigin: true },
      // Memory board (phase 01 residue cards): sparta explorer API proxies
      // /api/memory/* through to the memory daemon.
      '/api/memory': { target: 'http://127.0.0.1:3001', changeOrigin: true },
      '/api': { target: 'http://127.0.0.1:8790', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
