import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'node:path'

export default defineConfig({
  resolve: {
    alias: {
      '@embry/logo/react': resolve('/home/graham/workspace/experiments/embry-os/packages/embry-logo/src/react.tsx'),
    },
  },
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5180,
    strictPort: true,
    fs: {
      allow: [
        '/home/graham/.pi/skills/extract-pdf/viewer',
        '/home/graham/workspace/experiments/embry-os/packages/embry-logo',
      ],
    },
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
})
