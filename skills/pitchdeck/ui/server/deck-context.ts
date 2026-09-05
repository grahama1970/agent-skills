import { readFileSync, realpathSync, readdirSync, existsSync } from 'node:fs'
import { dirname, join, relative, isAbsolute, sep } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'

export interface DeckContext {
  directory: string
  url: string
  receipt: { operation: string; outputs: { document_path?: string; asset_base?: string; bundle_dir?: string; output_dir?: string; deck_data?: string } }
  deck: { deck_id: string; title: string; revision: number; slides: { id: string; hidden?: boolean }[] }
}

function contained(root: string, path: string) {
  const rel = relative(root, path)
  return !isAbsolute(rel) && rel !== '..' && !rel.startsWith(`..${sep}`)
}

export function resolveDeck(root: string, requested: string): DeckContext {
  const base = realpathSync(root)
  if (!requested.startsWith('/') || requested.startsWith('//') || /[?#\\]/.test(requested)) throw new Error('Invalid deck URL')
  const file = realpathSync(join(base, decodeURIComponent(requested)))
  if (!contained(base, file) || !file.endsWith('/deck.data.json')) throw new Error('Deck must be an emitted deck.data.json inside public/')
  const directory = dirname(file)
  const receipt = JSON.parse(readFileSync(join(directory, 'emit_ui_receipt.json'), 'utf8'))
  const deck = JSON.parse(readFileSync(file, 'utf8'))
  if (deck.seam_validation?.status !== 'PASS' || !Array.isArray(deck.slides)) throw new Error('Unvalidated deck')
  if (!['emit-ui', 'emit-document-ui'].includes(receipt.operation) || realpathSync(receipt.outputs.deck_data) !== file) throw new Error('Receipt does not identify this deck')
  return { directory, url: '/' + relative(base, file).split(sep).map(encodeURIComponent).join('/'), receipt, deck }
}

const contexts = new WeakMap<IncomingMessage, DeckContext>()
const pendingWrites = new Set<string>()
export function deckContext(req: IncomingMessage) {
  const context = contexts.get(req)
  if (!context) throw new Error('No active deck selected')
  return context
}

/** Explicit header for API callers; same-origin full Referer for existing UI callers.
 * Missing/ambiguous identity refuses rather than falling back to another deck. */
export function bindDeck(root: string, req: IncomingMessage, res: ServerResponse, next: () => void) {
  if (!req.url?.startsWith('/api/')) return next()
  try {
    const host = req.headers.host || ''
    const origin = `http://${host}`
    if (!['localhost', '127.0.0.1', '[::1]'].includes(new URL(origin).hostname)) throw new Error('Localhost only')
    if (req.headers.origin && req.headers.origin !== origin) throw new Error('Cross-origin request refused')
    if (req.headers['sec-fetch-site'] && !['same-origin', 'none'].includes(String(req.headers['sec-fetch-site']))) throw new Error('Cross-site request refused')
    if (req.url === '/api/decks') return next()
    let selected = req.headers['x-pitchdeck-deck']
    if (Array.isArray(selected)) throw new Error('Ambiguous deck')
    if (!selected) {
      if (!req.headers.referer) throw new Error('Active deck identity required (X-Pitchdeck-Deck)')
      const page = new URL(req.headers.referer)
      if (page.origin !== origin) throw new Error('Cross-origin referer refused')
      const url = new URL(page.searchParams.get('deck') || './deck.data.json', page)
      if (url.origin !== origin) throw new Error('Remote deck is read-only')
      selected = url.pathname
    }
    const context = resolveDeck(root, selected)
    const sourcePath = context.receipt.outputs.document_path || context.receipt.outputs.bundle_dir
    if (req.method === 'POST' && !req.url.startsWith('/api/debugger') && (!sourcePath || !existsSync(sourcePath))) throw new Error('Active deck source is missing. This preview is read-only; re-emit from a retained source before editing or exporting.')
    if (req.method === 'POST' && !['/api/debugger', '/api/element-agent/selection', '/api/element-agent/propose'].some(route => req.url!.startsWith(route))) {
      const source = context.receipt.outputs.document_path || context.receipt.outputs.bundle_dir || context.directory
      if (pendingWrites.has(source)) throw new Error('Another operation on this deck is pending')
      pendingWrites.add(source)
      const release = () => pendingWrites.delete(source)
      res.once('finish', release)
      res.once('close', release)
    }
    if (context.receipt.operation === 'emit-document-ui' && !['/api/slide-edit', '/api/export', '/api/debugger', '/api/deck-op', '/api/asset-drop', '/api/insert', '/api/element-agent'].some(route => req.url!.startsWith(route)) && req.method === 'POST') throw new Error('This operation requires a legacy bundle. Canonical decks support element editing, export and debugger control; no other deck will be modified.')
    contexts.set(req, context)
    next()
  } catch (error) {
    res.statusCode = 409
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify({ error: String(error) }))
  }
}

export function listDecks(root: string) {
  const result: { url: string; title: string; revision: number; source_available: boolean }[] = []
  function scan(directory: string, depth: number) {
    if (existsSync(join(directory, 'deck.data.json'))) {
      try {
        const item = resolveDeck(root, '/' + relative(root, join(directory, 'deck.data.json')).split(sep).join('/'))
        result.push({ url: item.url, title: item.deck.title, revision: item.deck.revision, source_available: existsSync(item.receipt.outputs.document_path || item.receipt.outputs.bundle_dir || '') })
      } catch { /* Not an emitted, validated deck: never offer it as writable. */ }
    }
    if (depth > 0) for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory() && !['assets', 'exports'].includes(entry.name)) scan(join(directory, entry.name), depth - 1)
    }
  }
  scan(root, 2)
  return result
}
