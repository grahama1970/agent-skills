import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

// Canonical shared UI package (agent-skills/skills/ux-lab/ui), imported from
// source via alias so the dependency stays versioned in this repo.
const uxLabUi = fileURLToPath(new URL('../../ux-lab/ui', import.meta.url))

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@ux-lab/ui': uxLabUi } },
  server: { port: 3006, fs: { allow: ['.', uxLabUi] } },
})
