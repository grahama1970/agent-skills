import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { execFile } from 'node:child_process'
import { createReadStream, existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'
import { defineConfig } from 'vite'
import { bindDeck, deckContext, listDecks } from './server/deck-context'
import { canonicalExport } from './server/canonical-export'
import { debuggerApi } from './server/debugger-api'

// Canonical shared UI package (agent-skills/skills/ux-lab/ui), imported from
// source via alias so the dependency stays versioned in this repo.
const uxLabUi = fileURLToPath(new URL('../../ux-lab/ui', import.meta.url))

const skillRoot = fileURLToPath(new URL('..', import.meta.url))
const publicDir = fileURLToPath(new URL('./public', import.meta.url))

// Dev-only edit bridge: POST /api/slide-edit → run.sh apply-edit. All
// validation lives in Python (the same fail-closed gates as the build); a
// rejected edit changes nothing on disk. The bundle dir comes from the
// emit_ui_receipt.json written next to deck.data.json — never from the client.

// Canonical documents route structural edits through `document-op` (full-model
// revalidation, nothing written on rejection). Args are fixed shapes only.
function documentOp(context: ReturnType<typeof deckContext>, args: string[], res: import('node:http').ServerResponse, timeout = 60_000, cleanup?: () => void) {
  const o = context.receipt.outputs
  execFile(`${skillRoot}/run.sh`, ['document-op', '--document', o.document_path!, '--output-dir', o.output_dir!, '--asset-base', o.asset_base!, ...args], { timeout }, (error, stdout, stderr) => {
    cleanup?.()
    res.setHeader('Content-Type', 'application/json')
    if (error) { res.statusCode = 422; res.end(JSON.stringify({ error: stderr.trim().split('\n').filter(l => l.includes('ERROR')).join(' ') || stderr.trim().slice(-400) || String(error) })); return }
    res.end(stdout)
  })
}

function slideEditApi(): Plugin {
  return {
    name: 'deck-slide-edit-api',
    configureServer(server) {
      // Emitted decks/exports land in public/ after startup and are excluded
      // from the file watcher (inotify ENOSPC crashed the server), so Vite's
      // cached public-file list never learns them. Serve them from disk.
      const types: Record<string, string> = { '.json': 'application/json', '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pdf': 'application/pdf', '.png': 'image/png', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.mp4': 'video/mp4', '.webm': 'video/webm', '.md': 'text/markdown', '.html': 'text/html', '.gif': 'image/gif', '.ico': 'image/x-icon', '.css': 'text/css' }
      server.middlewares.use((req, res, next) => {
        const pathname = decodeURIComponent(new URL(req.url || '/', 'http://localhost').pathname)
        const ext = extname(pathname)
        if (!types[ext] || pathname.includes('..')) return next()
        const file = join(publicDir, pathname)
        if (!file.startsWith(publicDir) || !existsSync(file) || !statSync(file).isFile()) return next()
        res.setHeader('Content-Type', types[ext])
        res.setHeader('Cache-Control', 'no-store')
        createReadStream(file).pipe(res)
      })
      server.middlewares.use((req, res, next) => bindDeck(publicDir, req, res, next))
      server.middlewares.use('/api/debugger', debuggerApi(skillRoot))
      server.middlewares.use('/api/insert', (req, res) => {
        if (req.method !== 'POST') { res.statusCode = 405; res.end(JSON.stringify({ error: 'POST only' })); return }
        const chunks: Buffer[] = []
        req.on('data', (c: Buffer) => chunks.push(c))
        req.on('end', () => {
          try {
            const { kind, slide_id, text, spec, chart_type, title, alt } = JSON.parse(Buffer.concat(chunks).toString('utf-8')) as Record<string, string>
            const ctx = deckContext(req)
            if (ctx.receipt.operation !== 'emit-document-ui') { res.statusCode = 422; res.end(JSON.stringify({ error: 'Insert is available on canonical documents; legacy bundles use the visual/asset workflow' })); return }
            if (!slide_id) { res.statusCode = 400; res.end(JSON.stringify({ error: 'slide_id required' })); return }
            if (kind === 'text') { documentOp(ctx, ['--op', 'add-text', '--slide-id', slide_id, '--text', text || 'New text'], res); return }
            if (kind !== 'chart' && kind !== 'diagram') { res.statusCode = 400; res.end(JSON.stringify({ error: 'kind must be text, chart or diagram' })); return }
            if (!spec || !alt) { res.statusCode = 400; res.end(JSON.stringify({ error: 'spec and alt are required' })); return }
            const tmpDir = mkdtempSync(join(tmpdir(), 'deck-insert-'))
            const specPath = join(tmpDir, kind === 'chart' ? 'metrics.json' : 'scene.yml')
            writeFileSync(specPath, spec)
            const args = ['--op', `add-${kind}`, '--slide-id', slide_id, '--spec', specPath, '--alt', alt]
            if (kind === 'chart') args.push('--chart-type', chart_type || 'bar', '--title', title || 'Figure')
            documentOp(ctx, args, res, 240_000, () => rmSync(tmpDir, { recursive: true, force: true }))
          } catch (error) { res.statusCode = 400; res.end(JSON.stringify({ error: String(error) })) }
        })
      })
      server.middlewares.use('/api/decks', (req, res) => {
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify(listDecks(publicDir)))
      })
      server.middlewares.use('/api/deck-context', (req, res) => {
        const c = deckContext(req)
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify({ url: c.url, deck_id: c.deck.deck_id, title: c.deck.title, revision: c.deck.revision, source: c.receipt.operation }))
      })
      server.middlewares.use('/api/deck-op', (req, res) => {
        const publicDir = deckContext(req).directory
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
            const ctx = deckContext(req)
            if (ctx.receipt.operation === 'emit-document-ui') {
              if (base_revision !== undefined && Number(base_revision) !== ctx.deck.revision) { res.statusCode = 409; res.end(JSON.stringify({ error: 'Stale deck revision; reload before editing' })); return }
              documentOp(ctx, ['--op', `slide-${op}`, '--slide-id', String(slide_id)], res)
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
        const publicDir = deckContext(req).directory
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
      server.middlewares.use('/api/record-transcript', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end(JSON.stringify({ error: 'POST only' }))
          return
        }
        execFile(
          `${skillRoot}/run.sh`,
          ['record-transcript'],
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
      })
      server.middlewares.use('/api/claim-decide', (req, res) => {
        const publicDir = deckContext(req).directory
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
        const publicDir = deckContext(req).directory
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
        const publicDir = deckContext(req).directory
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
        const publicDir = deckContext(req).directory
        const receiptPath = `${publicDir}/emit_ui_receipt.json`
        if (req.method === 'GET') {
          try {
            const receipt = JSON.parse(readFileSync(receiptPath, 'utf-8'))
            const bundleDir = receipt?.outputs?.bundle_dir
            res.setHeader('Content-Type', 'application/json')
            const source = receipt.operation === 'emit-document-ui' ? receipt.outputs.document_path : `${bundleDir}/deck.public.yaml`
            res.end(JSON.stringify({ yaml: readFileSync(source, 'utf-8') }))
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
        const publicDir = deckContext(req).directory
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
            const ctx = deckContext(req)
            if (ctx.receipt.operation === 'emit-document-ui') {
              if (action === 'clear') { res.statusCode = 422; res.end(JSON.stringify({ error: 'Select the image and delete it instead' })); return }
              if (!slide_id || !filename || !alt || !data_b64) { res.statusCode = 400; res.end(JSON.stringify({ error: 'slide_id, filename, alt, data_b64 are required' })); return }
              const tmpDir = mkdtempSync(join(tmpdir(), 'deck-drop-'))
              const tmpPath = join(tmpDir, filename.replace(/[^a-zA-Z0-9._-]/g, '_'))
              writeFileSync(tmpPath, Buffer.from(data_b64, 'base64'))
              documentOp(ctx, ['--op', 'add-image', '--slide-id', slide_id, '--file', tmpPath, '--alt', alt], res, 60_000, () => rmSync(tmpDir, { recursive: true, force: true }))
              return
            }
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
        const publicRoot = server.config.publicDir
        const context = deckContext(req)
        const publicDir = context.directory
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
            if (context.receipt.operation === 'emit-document-ui') {
              void canonicalExport(skillRoot, publicRoot, context, String(format)).then(
                result => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(result)) },
                error => { res.statusCode = 422; res.end(JSON.stringify({ error: String(error) })) },
              )
              return
            }
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
              const prefix = context.url.slice(0, -'deck.data.json'.length).replace(/\/$/, '')
              res.end(JSON.stringify({ url: prefix + url, deck_id: context.deck.deck_id, revision: context.deck.revision }))
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
        const publicDir = deckContext(req).directory
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
            // Document-pipeline decks (#1388) edit the canonical document;
            // legacy bundle decks keep the apply-edit path unchanged.
            const isDocument = receipt?.operation === 'emit-document-ui'
            const structural = String(field).match(/^element:(del|crop):(.+)$/)
            if (isDocument && structural) {
              const ctx = deckContext(req)
              if (base_revision !== undefined && Number(base_revision) !== ctx.deck.revision) { res.statusCode = 409; res.end(JSON.stringify({ error: 'Stale deck revision; reload before editing' })); return }
              documentOp(ctx, ['--op', structural[1] === 'del' ? 'delete-element' : 'crop', '--slide-id', String(slide_id), '--element-id', structural[2], ...(structural[1] === 'crop' && value ? ['--bbox', String(value)] : [])], res)
              return
            }
            if (isDocument && base_revision !== undefined && Number(base_revision) !== deckContext(req).deck.revision) {
              res.statusCode = 409
              res.end(JSON.stringify({ error: 'Stale deck revision; reload before editing' }))
              return
            }
            const bundleDir = receipt?.outputs?.bundle_dir
            if (!isDocument && !bundleDir) {
              res.statusCode = 409
              res.end(JSON.stringify({ error: 'emit_ui_receipt.json has no bundle_dir; re-run emit-ui first' }))
              return
            }
            execFile(
              `${skillRoot}/run.sh`,
              isDocument
                ? [
                    'document-edit',
                    '--document', receipt.outputs.document_path,
                    '--output-dir', receipt.outputs.output_dir,
                    '--asset-base', receipt.outputs.asset_base,
                    '--slide-id', String(slide_id),
                    '--field', String(field),
                    '--value', String(value),
                  ]
                : [
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
  resolve: { alias: { '@ux-lab/ui': uxLabUi }, dedupe: ['react', 'react-dom'] },
  // The vendored shared-chat family under @ux-lab/ui lives outside this
  // package root, so Vite's dependency scanner never sees its bare imports —
  // force them through the optimizer (root-resolved) or import-analysis fails.
  optimizeDeps: {
    include: [
      'react-markdown',
      'remark-gfm',
      'remark-math',
      'rehype-katex',
      'framer-motion',
      'prismjs',
      'react-simple-code-editor',
      'react-syntax-highlighter',
      'react-syntax-highlighter/dist/esm/styles/prism',
      'recharts',
      '@xyflow/react',
      'dagre',
      'lucide-react',
    ],
  },
  server: { port: 3006, fs: { allow: ['.', uxLabUi] }, // public/ is not watched at all: emitted decks create new dirs at runtime and
  // this workstation's inotify budget is routinely exhausted by other tools, which
  // killed the server. Public files are served from disk by the middleware above.
  watch: { ignored: [`${publicDir}/**`] } },
})
