import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { execFile } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
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
            const { op, slide_id, target_order, base_revision } = JSON.parse(body) as Record<string, string | number>
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
              ['deck-op', '--bundle-dir', bundleDir, '--output-dir', publicDir, '--op', String(op), '--slide-id', String(slide_id), ...(target_order ? ['--target-order', String(target_order)] : []), ...(base_revision !== undefined ? ['--base-revision', String(base_revision)] : []), '--json'],
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
      server.middlewares.use('/api/record-note', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        let body = ''
        req.on('data', (chunk) => (body += chunk))
        req.on('end', () => {
          try {
            const { slide_id } = JSON.parse(body) as Record<string, string>
            const receipt = JSON.parse(readFileSync(`${publicDir}/emit_ui_receipt.json`, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            if (!bundleDir || !slide_id) {
              res.statusCode = 400
              res.end(JSON.stringify({ error: 'slide_id required' }))
              return
            }
            execFile(
              `${skillRoot}/run.sh`,
              ['record-note', '--bundle-dir', bundleDir, '--output-dir', publicDir, '--slide-id', String(slide_id)],
              { timeout: 180_000 },
              (error, stdout, stderr) => {
                res.setHeader('Content-Type', 'application/json')
                try {
                  JSON.parse(stdout)
                  res.end(stdout)
                } catch {
                  res.statusCode = 422
                  res.end(JSON.stringify({ error: stderr.trim().slice(-300) || String(error) }))
                }
              },
            )
          } catch (error) {
            res.statusCode = 400
            res.end(JSON.stringify({ error: String(error) }))
          }
        })
      })
      server.middlewares.use('/api/claim-decide', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        let body = ''
        req.on('data', (chunk) => (body += chunk))
        req.on('end', () => {
          try {
            const { claim_id, decision, decided_by, qualifier, batch } = JSON.parse(body) as Record<string, string | boolean>
            const receipt = JSON.parse(readFileSync(`${publicDir}/emit_ui_receipt.json`, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            if (!bundleDir || !claim_id || !decision || !decided_by) {
              res.statusCode = 400
              res.end(JSON.stringify({ error: 'claim_id, decision, decided_by required' }))
              return
            }
            const args = ['claim-decide', '--bundle-dir', bundleDir, '--output-dir', publicDir, '--claim-id', String(claim_id), '--decision', String(decision), '--decided-by', String(decided_by), '--json']
            if (qualifier) args.push('--qualifier', String(qualifier))
            if (batch) args.push('--batch')
            execFile(`${skillRoot}/run.sh`, args, { timeout: 60_000 }, (error, stdout, stderr) => {
              res.setHeader('Content-Type', 'application/json')
              if (error) {
                res.statusCode = 422
                res.end(JSON.stringify({ error: stderr.trim() || String(error) }))
                return
              }
              res.end(stdout)
            })
          } catch (error) {
            res.statusCode = 400
            res.end(JSON.stringify({ error: String(error) }))
          }
        })
      })
      server.middlewares.use('/api/simulate', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        let body = ''
        req.on('data', (chunk) => (body += chunk))
        req.on('end', () => {
          try {
            const { slide_id, field, value, op, target_order } = JSON.parse(body) as Record<string, string | number>
            const receipt = JSON.parse(readFileSync(`${publicDir}/emit_ui_receipt.json`, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            if (!bundleDir || !slide_id) {
              res.statusCode = 400
              res.end(JSON.stringify({ error: 'bundle_dir and slide_id required' }))
              return
            }
            const args = ['simulate', '--bundle-dir', bundleDir, '--slide-id', String(slide_id)]
            if (field) args.push('--field', String(field), '--value', String(value ?? ''))
            if (op) args.push('--op', String(op))
            if (target_order) args.push('--target-order', String(target_order))
            execFile(`${skillRoot}/run.sh`, args, { timeout: 60_000 }, (error, stdout) => {
              res.setHeader('Content-Type', 'application/json')
              // simulate exits 3 on would_pass=false but still prints JSON
              try {
                JSON.parse(stdout)
                res.end(stdout)
              } catch {
                res.statusCode = 422
                res.end(JSON.stringify({ error: String(error) }))
              }
            })
          } catch (error) {
            res.statusCode = 400
            res.end(JSON.stringify({ error: String(error) }))
          }
        })
      })
      server.middlewares.use('/api/undo', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        try {
          const receipt = JSON.parse(readFileSync(`${publicDir}/emit_ui_receipt.json`, 'utf-8'))
          const bundleDir = receipt?.outputs?.bundle_dir
          if (!bundleDir) {
            res.statusCode = 409
            res.end(JSON.stringify({ error: 'emit_ui_receipt.json has no bundle_dir; re-run emit-ui first' }))
            return
          }
          execFile(
            `${skillRoot}/run.sh`,
            ['undo', '--bundle-dir', bundleDir, '--output-dir', publicDir, '--json'],
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
      server.middlewares.use('/api/source', (req, res) => {
        const receiptPath = `${publicDir}/emit_ui_receipt.json`
        if (req.method === 'GET') {
          try {
            const receipt = JSON.parse(readFileSync(receiptPath, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ yaml: readFileSync(`${bundleDir}/deck.public.yaml`, 'utf-8') }))
          } catch (error) {
            res.statusCode = 500
            res.end(JSON.stringify({ error: String(error) }))
          }
          return
        }
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'GET or POST only' }))
          return
        }
        const chunks: Buffer[] = []
        req.on('data', (chunk: Buffer) => chunks.push(chunk))
        req.on('end', () => {
          try {
            const { yaml: sourceYaml } = JSON.parse(Buffer.concat(chunks).toString('utf-8')) as { yaml?: string }
            if (!sourceYaml) {
              res.statusCode = 400
              res.end(JSON.stringify({ error: 'yaml is required' }))
              return
            }
            const receipt = JSON.parse(readFileSync(receiptPath, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            const tmpDir = mkdtempSync(join(tmpdir(), 'deck-source-'))
            const tmpPath = join(tmpDir, 'deck.yaml')
            writeFileSync(tmpPath, sourceYaml)
            execFile(
              `${skillRoot}/run.sh`,
              ['source-edit', '--bundle-dir', bundleDir, '--output-dir', publicDir, '--source-file', tmpPath, '--json'],
              { timeout: 60_000 },
              (error, stdout, stderr) => {
                rmSync(tmpDir, { recursive: true, force: true })
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
      server.middlewares.use('/api/asset-drop', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        const chunks: Buffer[] = []
        req.on('data', (chunk: Buffer) => chunks.push(chunk))
        req.on('end', () => {
          try {
            const { slide_id, filename, alt, data_b64, action } = JSON.parse(
              Buffer.concat(chunks).toString('utf-8'),
            ) as Record<string, string>
            const receipt = JSON.parse(readFileSync(`${publicDir}/emit_ui_receipt.json`, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            if (!bundleDir) {
              res.statusCode = 409
              res.end(JSON.stringify({ error: 'emit_ui_receipt.json has no bundle_dir; re-run emit-ui first' }))
              return
            }
            const respond = (error: Error | null, stdout: string, stderr: string) => {
              res.setHeader('Content-Type', 'application/json')
              if (error) {
                res.statusCode = 422
                res.end(JSON.stringify({ error: stderr.trim() || String(error) }))
                return
              }
              res.end(stdout)
            }
            if (action === 'clear') {
              execFile(
                `${skillRoot}/run.sh`,
                ['asset-clear', '--bundle-dir', bundleDir, '--output-dir', publicDir, '--slide-id', slide_id, '--json'],
                { timeout: 60_000 },
                respond,
              )
              return
            }
            if (!slide_id || !filename || !alt || !data_b64) {
              res.statusCode = 400
              res.end(JSON.stringify({ error: 'slide_id, filename, alt, data_b64 are required' }))
              return
            }
            const safeName = filename.replace(/[^a-zA-Z0-9._-]/g, '_')
            const tmpDir = mkdtempSync(join(tmpdir(), 'deck-drop-'))
            const tmpPath = join(tmpDir, safeName)
            writeFileSync(tmpPath, Buffer.from(data_b64, 'base64'))
            execFile(
              `${skillRoot}/run.sh`,
              [
                'asset-add',
                '--bundle-dir', bundleDir,
                '--output-dir', publicDir,
                '--slide-id', slide_id,
                '--file', tmpPath,
                '--alt', alt,
                '--json',
              ],
              { timeout: 120_000 },
              (error, stdout, stderr) => {
                rmSync(tmpDir, { recursive: true, force: true })
                respond(error, stdout, stderr)
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
              execFile(
                `${skillRoot}/run.sh`,
                [...buildArgs.slice(0, -1), `${exportsDir}/deck.draft.pptx`, '--draft-watermark'],
                { timeout: 120_000 },
                (error, _stdout, stderr) => finish(error, stderr, '/exports/deck.draft.pptx'),
              )
            } else if (format === 'pptx-publish') {
              execFile(
                `${skillRoot}/run.sh`,
                [...buildArgs, '--require-approved-claims'],
                { timeout: 120_000 },
                (error, _stdout, stderr) => finish(error, stderr, '/exports/deck.pptx'),
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
            } else if (format === 'html') {
              execFile(
                `${skillRoot}/run.sh`,
                ['emit-html', '--bundle-dir', bundleDir, '--output', `${exportsDir}/deck.html`],
                { timeout: 120_000 },
                (error, _stdout, stderr) => finish(error, stderr, '/exports/deck.html'),
              )
            } else if (format === 'md') {
              execFile(
                `${skillRoot}/run.sh`,
                ['emit-md', '--bundle-dir', bundleDir, '--output-dir', `${exportsDir}/md`],
                { timeout: 120_000 },
                (error, _stdout, stderr) => finish(error, stderr, '/exports/md/deck.md'),
              )
            } else {
              res.statusCode = 400
              res.end(JSON.stringify({ error: "format must be 'pptx', 'pdf', 'html', or 'md'" }))
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
            const { slide_id, field, value, base_revision } = JSON.parse(body) as Record<string, string | number>
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
                '--slide-id', String(slide_id),
                '--field', String(field),
                '--value', String(value),
                ...(base_revision !== undefined ? ['--base-revision', String(base_revision)] : []),
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
