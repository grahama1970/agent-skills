/** Eval runner: bundle render_dream_workspace.tsx with esbuild, pinning react
 * to ux/app's copy (a stray ~/node_modules symlink otherwise leaks a second
 * React from pi-mono and breaks hooks), then execute the bundle. */
import { build } from 'esbuild'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const appRoot = resolve(here, '../..')
const outfile = join(mkdtempSync(join(tmpdir(), 'pd-render-eval-')), 'render.cjs')

await build({
  entryPoints: [join(here, 'render_dream_workspace.tsx')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  outfile,
  logLevel: 'silent',
  alias: {
    'pd-ui': process.env.PD_UI_SRC ?? resolve(appRoot, '../../ui/src/index.ts'),
    react: resolve(appRoot, 'node_modules/react'),
    'react-dom': resolve(appRoot, 'node_modules/react-dom'),
    'framer-motion': resolve(appRoot, 'node_modules/framer-motion'),
    d3: resolve(appRoot, 'node_modules/d3'),
    'lucide-react': resolve(appRoot, 'node_modules/lucide-react'),
  },
})

await import(pathToFileURL(outfile).href)
