import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { execFile } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'
import { defineConfig } from 'vite'

// Canonical shared UI package (agent-skills/skills/ux-lab/ui), imported from
// source via alias so the dependency stays versioned in this repo.
const uxLabUi = fileURLToPath(new URL('../../ux-lab/ui', import.meta.url))

const skillRoot = fileURLToPath(new URL('..', import.meta.url))
const publicDir = fileURLToPath(new URL('./public', import.meta.url))

// Dev-only edit bridge: POST /api/slide-edit → run.sh apply-edit. All
// validation lives in Python (the same fail-closed gates as the build); a
// rejected edit changes nothing on disk. The bundle dir comes from the
// emit_ui_receipt.json written next to deck.data.json — never from the client.
function slideEditApi(): Plugin {
  return {
    name: 'deck-slide-edit-api',
    configureServer(server) {
      server.middlewares.use('/api/deck-op', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        let body = ''
        req.on('data', (chunk) => (body += chunk))
        req.on('end', () => {
          try {
            const { op, slide_id } = JSON.parse(body) as Record<string, string>
            if (!op || !slide_id) {
              res.statusCode = 400
              res.end(JSON.stringify({ error: 'op and slide_id are required' }))
              return
            }
            const receipt = JSON.parse(readFileSync(`${publicDir}/emit_ui_receipt.json`, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            if (!bundleDir) {
              res.statusCode = 409
              res.end(JSON.stringify({ error: 'emit_ui_receipt.json has no bundle_dir; re-run emit-ui first' }))
              return
            }
            execFile(
              `${skillRoot}/run.sh`,
              ['deck-op', '--bundle-dir', bundleDir, '--output-dir', publicDir, '--op', op, '--slide-id', slide_id, '--json'],
              { timeout: 60_000 },
              (error, stdout, stderr) => {
                res.setHeader('Content-Type', 'application/json')
                if (error) {
                  res.statusCode = 422
                  res.end(JSON.stringify({ error: stderr.trim() || String(error) }))
                  return
                }
                res.end(stdout)
              },
            )
          } catch (error) {
            res.statusCode = 400
            res.end(JSON.stringify({ error: String(error) }))
          }
        })
      })
      server.middlewares.use('/api/export', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        let body = ''
        req.on('data', (chunk) => (body += chunk))
        req.on('end', () => {
          try {
            const { format } = JSON.parse(body) as { format?: string }
            const receipt = JSON.parse(readFileSync(`${publicDir}/emit_ui_receipt.json`, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            if (!bundleDir) {
              res.statusCode = 409
              res.end(JSON.stringify({ error: 'emit_ui_receipt.json has no bundle_dir; re-run emit-ui first' }))
              return
            }
            const exportsDir = `${publicDir}/exports`
            const finish = (error: Error | null, stderr: string, url: string) => {
              res.setHeader('Content-Type', 'application/json')
              if (error) {
                res.statusCode = 422
                res.end(JSON.stringify({ error: stderr.trim() || String(error) }))
                return
              }
              res.end(JSON.stringify({ url }))
            }
            const buildArgs = [
              'build',
              '--deck', `${bundleDir}/deck.public.yaml`,
              '--claim-ledger', `${bundleDir}/claim_ledger.yaml`,
              '--source-manifest', `${bundleDir}/source_manifest.resolved.yaml`,
              '--asset-manifest', `${bundleDir}/asset_manifest.yaml`,
              '--output', `${exportsDir}/deck.pptx`,
            ]
            if (format === 'pptx') {
              execFile(`${skillRoot}/run.sh`, buildArgs, { timeout: 120_000 }, (error, _stdout, stderr) =>
                finish(error, stderr, '/exports/deck.pptx'),
              )
            } else if (format === 'pdf') {
              execFile(`${skillRoot}/run.sh`, buildArgs, { timeout: 120_000 }, (buildError, _stdout, buildStderr) => {
                if (buildError) return finish(buildError, buildStderr, '')
                execFile(
                  `${skillRoot}/run.sh`,
                  ['render', '--pptx', `${exportsDir}/deck.pptx`, '--output-dir', `${exportsDir}/render`],
                  { timeout: 300_000 },
                  (error, _stdout2, stderr) => finish(error, stderr, '/exports/render/deck.pdf'),
                )
              })
            } else if (format === 'md') {
              execFile(
                `${skillRoot}/run.sh`,
                ['emit-md', '--bundle-dir', bundleDir, '--output-dir', `${exportsDir}/md`],
                { timeout: 120_000 },
                (error, _stdout, stderr) => finish(error, stderr, '/exports/md/deck.md'),
              )
            } else {
              res.statusCode = 400
              res.end(JSON.stringify({ error: "format must be 'pptx', 'pdf', or 'md'" }))
            }
          } catch (error) {
            res.statusCode = 400
            res.end(JSON.stringify({ error: String(error) }))
          }
        })
      })
      server.middlewares.use('/api/slide-edit', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        let body = ''
        req.on('data', (chunk) => (body += chunk))
        req.on('end', () => {
          try {
            const { slide_id, field, value } = JSON.parse(body) as Record<string, string>
            if (!slide_id || !field || typeof value !== 'string') {
              res.statusCode = 400
              res.end(JSON.stringify({ error: 'slide_id, field, value are required' }))
              return
            }
            const receipt = JSON.parse(readFileSync(`${publicDir}/emit_ui_receipt.json`, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            if (!bundleDir) {
              res.statusCode = 409
              res.end(JSON.stringify({ error: 'emit_ui_receipt.json has no bundle_dir; re-run emit-ui first' }))
              return
            }
            execFile(
              `${skillRoot}/run.sh`,
              [
                'apply-edit',
                '--bundle-dir', bundleDir,
                '--output-dir', publicDir,
                '--slide-id', slide_id,
                '--field', field,
                '--value', value,
                '--json',
              ],
              { timeout: 60_000 },
              (error, stdout, stderr) => {
                res.setHeader('Content-Type', 'application/json')
                if (error) {
                  res.statusCode = 422
                  res.end(JSON.stringify({ error: stderr.trim() || String(error) }))
                  return
                }
                res.end(stdout)
              },
            )
          } catch (error) {
            res.statusCode = 400
            res.end(JSON.stringify({ error: String(error) }))
          }
        })
      })
    },
  }
}

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss(), slideEditApi()],
  resolve: { alias: { '@ux-lab/ui': uxLabUi } },
  server: { port: 3006, fs: { allow: ['.', uxLabUi] } },
})
