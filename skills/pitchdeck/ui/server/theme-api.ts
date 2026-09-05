import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { deckContext } from './deck-context'
const exec = promisify(execFile)
export function themeApi(skillRoot: string) {
  return async (req: IncomingMessage, res: ServerResponse) => {
    let dir: string | undefined
    res.setHeader('Content-Type', 'application/json')
    try {
      const c = deckContext(req)
      let raw = ''
      for await (const chunk of req) { raw += chunk; if (raw.length > 8192) throw new Error('Theme request too large') }
      const body = req.method === 'GET' ? { action: 'list' } : JSON.parse(raw)
      if (!['GET', 'POST'].includes(req.method || '')) throw new Error('GET or POST required')
      dir = mkdtempSync(join(tmpdir(), 'pitchdeck-theme-'))
      const input = join(dir, 'request.json'); writeFileSync(input, JSON.stringify(body))
      const source = c.receipt.outputs.document_path || join(c.receipt.outputs.bundle_dir!, 'deck.public.yaml')
      const run = await exec(join(skillRoot, 'run.sh'), ['theme-edit', '--source', source, '--output-dir', c.directory, '--request-file', input, '--storage', '/mnt/storage12tb/skills/pitchdeck/outputs/themes'], { timeout: 30000 })
      res.end(run.stdout)
    } catch (error) {
      res.statusCode = 409
      res.end(JSON.stringify({ error: error instanceof Error && 'stderr' in error ? String(error.stderr).slice(-800) : String(error) }))
    } finally { if (dir) rmSync(dir, { recursive: true, force: true }) }
  }
}
