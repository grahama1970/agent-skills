import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { mkdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { createHash, randomUUID } from 'node:crypto'
import type { DeckContext } from './deck-context'

const exec = promisify(execFile)

export async function canonicalExport(skillRoot: string, publicRoot: string, context: DeckContext, format: string) {
  if (!['pptx', 'pdf'].includes(format)) throw new Error('Canonical documents support authoring PPTX/PDF previews here. Public delivery requires verify-publish; HTML/Marp use the bundle workflow.')
  const { document_path, asset_base } = context.receipt.outputs
  if (!document_path || !asset_base) throw new Error('Canonical receipt lacks document_path or asset_base')
  const directory = join(context.directory, 'exports', randomUUID())
  mkdirSync(directory, { recursive: true })
  const pptx = join(directory, 'deck.pptx')
  // The owning compiler retains its publish-authorization gate. No fake bundle
  // or approval is synthesized to make the canonical path look like legacy YAML.
  await exec(join(skillRoot, 'run.sh'), ['emit-document-pptx', '--document', document_path, '--asset-base', asset_base, '--output', pptx], { timeout: 120000 })
  let file = pptx
  if (format === 'pdf') {
    await exec(join(skillRoot, 'run.sh'), ['render', '--pptx', pptx, '--output-dir', join(directory, 'render')], { timeout: 300000 })
    file = join(directory, 'render', 'deck.pdf')
  }
  const bytes = readFileSync(file)
  return { url: '/' + relative(publicRoot, file).split('/').map(encodeURIComponent).join('/'), deck_id: context.deck.deck_id, revision: context.deck.revision, sha256: createHash('sha256').update(new Uint8Array(bytes)).digest('hex'), delivery: 'authoring-preview-not-publication-proof' }
}
