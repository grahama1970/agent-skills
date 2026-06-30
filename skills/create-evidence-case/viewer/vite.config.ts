import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'node:path'

export default defineConfig({
  resolve: {
    alias: {
      '@embry/logo/react': resolve('${HOME}/workspace/experiments/embry-os/packages/embry-logo/src/react.tsx'),
    },
  },
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5179,
    strictPort: true,
    fs: {
      allow: [
        '${HOME}/workspace/experiments/pi-mono/.pi/skills/create-evidence-case/viewer',
        '${HOME}/workspace/experiments/embry-os/packages/embry-logo',
      ],
    },
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
})
