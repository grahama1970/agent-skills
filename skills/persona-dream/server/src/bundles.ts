import { execFile } from 'node:child_process'
import { copyFile, mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { promisify } from 'node:util'
import type { DreamPathPolicy } from './paths'

const execFileAsync = promisify(execFile)

function safePart(value: unknown, fallback: string): string {
  return String(value ?? '').trim().replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 120) || fallback
}

export async function createPanelPromptBundle(options: {
  policy: DreamPathPolicy
  temporaryRoot: string
  filename: unknown
  entries: unknown
}): Promise<{ zipPath: string; entryCount: number }> {
  const filename = `${safePart(options.filename, 'persona-dream-panel-prompts').replace(/\.zip$/i, '')}.zip`
  if (!Array.isArray(options.entries) || options.entries.length === 0) throw new Error('entries_required')
  if (options.entries.length > 200) throw new Error('bundle_entry_limit_exceeded')
  const bundleId = `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
  const root = resolve(options.temporaryRoot, bundleId)
  const zipPath = resolve(options.temporaryRoot, `${bundleId}-${filename}`)
  await mkdir(root, { recursive: true })
  let totalBytes = 0
  for (const raw of options.entries) {
    const entry = raw as { name?: unknown; text?: unknown; path?: unknown }
    const name = safePart(entry.name, '')
    if (!name) throw new Error('invalid_bundle_entry_name')
    const destination = resolve(root, name)
    if (dirname(destination) !== root) throw new Error('bundle_entry_escaped_root')
    if (typeof entry.text === 'string') {
      totalBytes += Buffer.byteLength(entry.text)
      if (totalBytes > 25 * 1024 * 1024) throw new Error('bundle_size_limit_exceeded')
      await writeFile(destination, entry.text)
    } else if (typeof entry.path === 'string') {
      await copyFile(options.policy.resolveFile(entry.path), destination)
    } else {
      throw new Error('bundle_entry_requires_text_or_path')
    }
  }
  await execFileAsync('zip', ['-qr', zipPath, '.'], { cwd: root, timeout: 30_000, maxBuffer: 4 * 1024 * 1024 })
  return { zipPath, entryCount: options.entries.length }
}
