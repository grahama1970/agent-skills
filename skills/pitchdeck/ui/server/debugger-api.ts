import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { join, relative, isAbsolute, sep } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { deckContext, type DeckContext, type DeckElement } from './deck-context'

function allElements(elements: DeckElement[] = []): DeckElement[] {
  return elements.flatMap(e => [e, ...allElements(e.children)])
}

const exec = promisify(execFile)
interface Mapping { file: string; line: number; endLine?: number; endColumn?: number; breakLine?: number; launch?: string; locals?: string[]; concepts?: Record<string, Mapping> }
interface Session { vscodeSessionId: string; stopSequence: number; selectedThreadId?: number }
interface BridgeStatus { id?: string; status: string; proofValid?: boolean; sessionState?: Session; [key: string]: unknown }
const states = new Map<string, { path?: string; session?: Session; busy: boolean }>()
let workspaceBusy = false

function mapping(context: DeckContext, workspace: string, slide: string, concept = ''): Mapping | null {
  const selected = context.deck.slides.find(s => s.id === slide && !s.hidden)
  if (!selected) throw new Error('Slide not in active deck')
  const path = join(context.directory, 'debugger.json')
  if (!existsSync(path)) return null
  const config = JSON.parse(readFileSync(path, 'utf8'))
  if (config.schema !== 'pitchdeck.debugger_map.v1') throw new Error('Invalid debugger map schema')
  const base: Mapping = config.slides?.[slide]
  if (!base) return null
  if (concept && !allElements(selected.elements).some(e => e.id === concept)) throw new Error('Concept not in active slide')
  const item = concept ? base.concepts?.[concept] : base
  if (!item) throw new Error('Concept has no source mapping')
  if (typeof item.file !== 'string' || isAbsolute(item.file)) throw new Error('Mapped file must be workspace-relative')
  const file = realpathSync(join(workspace, item.file))
  const rel = relative(workspace, file)
  if (rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) throw new Error('Mapped file escapes approved workspace')
  const lines = readFileSync(file, 'utf8').split('\n')
  const endLine = item.endLine ?? item.line
  if (!Number.isSafeInteger(item.line) || item.line < 1 || !Number.isSafeInteger(endLine) || endLine < item.line || endLine > lines.length) throw new Error('Invalid mapped range')
  const endColumn = item.endColumn ?? lines[endLine - 1].length + 1
  if (!Number.isSafeInteger(endColumn) || endColumn < 1 || endColumn > lines[endLine - 1].length + 1 || (endLine === item.line && endColumn === 1)) throw new Error('Mapped selection must be nonempty and contained')
  if (item.locals && (!Array.isArray(item.locals) || item.locals.length > 20 || item.locals.some(n => typeof n !== 'string' || !/^[\w]+$/.test(n)))) throw new Error('Invalid local variable names')
  if (item.breakLine !== undefined && (!Number.isSafeInteger(item.breakLine) || item.breakLine < item.line || item.breakLine > endLine)) throw new Error('Breakpoint must be within mapped source range')
  const { concepts: _concepts, ...target } = item
  return { ...target, file, endLine, endColumn }
}

/** Local trusted-workspace adapter; browser supplies action/slide IDs, never commands,
 * workspace paths, watch expressions or debugger arguments. */
export function debuggerApi(skillRoot: string) {
  const workspace = realpathSync(process.env.PITCHDECK_DEBUG_WORKSPACE || join(skillRoot, '../..'))
  const debuggerRoot = join(skillRoot, '../debugger')
  return async (req: IncomingMessage, res: ServerResponse) => {
    res.setHeader('Content-Type', 'application/json')
    const context = deckContext(req)
    const state = states.get(context.url) || { busy: false }
    states.set(context.url, state)
    try {
      if (req.method === 'GET') {
        const slide = new URL(req.url || '/', 'http://localhost').searchParams.get('slide') || context.deck.slides[0]?.id
        const query = new URL(req.url || '/', 'http://localhost').searchParams
        const target = mapping(context, workspace, slide, query.get('concept') || '')
        const configPath = join(context.directory, 'debugger.json')
        const configured = existsSync(configPath) ? JSON.parse(readFileSync(configPath, 'utf8')).slides?.[slide]?.concepts || {} : {}
        const concepts = allElements(context.deck.slides.find(s => s.id === slide)?.elements).filter(e => Object.hasOwn(configured, e.id)).map(e => ({ id: e.id, label: e.text || e.id }))
        const receipt: BridgeStatus | null = state.path && existsSync(state.path) ? JSON.parse(readFileSync(state.path, 'utf8')) : null
        if (receipt?.sessionState) state.session = receipt.sessionState
        res.end(JSON.stringify({ mapping: target && { ...target, file: relative(workspace, target.file) }, concepts, workspace, receipt, session: state.session, busy: state.busy, status: !target ? 'unmapped' : receipt?.status || 'not-connected' }))
        return
      }
      if (req.method !== 'POST' || req.headers['x-pitchdeck-control'] !== '1') throw new Error('Explicit debugger control header required')
      // Serialize: a sync-triggered reveal may still be in flight when Run is clicked.
      for (let waited = 0; (workspaceBusy || state.busy) && waited < 15000; waited += 100) await new Promise(r => setTimeout(r, 100))
      if (workspaceBusy || state.busy) throw new Error('Debugger command already pending')
      let body = ''
      for await (const chunk of req) { body += chunk; if (body.length > 8192) throw new Error('Oversized debugger request') }
      const request = JSON.parse(body)
      const allowed = ['reveal', 'start', 'inspect', 'continue', 'stepOver', 'terminate']
      if (!allowed.includes(request.action)) throw new Error('Unsupported debugger action')
      if (request.concept_id !== undefined && typeof request.concept_id !== 'string') throw new Error('Invalid concept ID')
      const target = mapping(context, workspace, request.slide_id, request.concept_id || '')
      if (!target) {
        if (request.action === 'reveal') { res.end(JSON.stringify({ status: 'unmapped', mapping: null })); return }
        throw new Error('No debugger mapping for this slide; configure debugger.json beside the emitted deck')
      }
      const args = ['--workspace', workspace, '--workspace-artifacts', '--expect-extension-host-kind', process.env.PITCHDECK_DEBUG_HOST_KIND || 'ui', '--action', request.action, '--no-save-before-start']
      if (request.action === 'reveal') args.push('--reveal', `${target.file}:${target.line}:1:${target.endLine}:${target.endColumn}`)
      else if (request.action === 'start') {
        if (!target.launch || typeof target.launch !== 'string') throw new Error('Slide has no launch configuration')
        args.push('--launch-config-name', target.launch, '--break', `${target.file}:${target.breakLine ?? target.line}`)
      } else {
        const session = state.session
        if (!session || request.session_id !== session.vscodeSessionId || request.stop_sequence !== session.stopSequence) throw new Error('Stale or missing debugger session; inspect current state first')
        args.push('--session-id', session.vscodeSessionId, '--expected-stop-sequence', String(session.stopSequence))
        if (session.selectedThreadId) args.push('--thread-id', String(session.selectedThreadId))
      }
      for (const name of target.locals || []) args.push('--local', name, '--expand', `${name}:1`)
      state.busy = true
      workspaceBusy = true
      try {
        // Documented $debugger writer. Workspace artifacts are explicitly
        // supported for hosts whose XDG runtime tmpfs is full; paths stay ignored.
        const { stdout } = await exec('uv', ['run', '--project', debuggerRoot, 'python', join(debuggerRoot, 'scripts/request_vscode_bridge.py'), ...args], {
          timeout: 20000, env: { ...process.env, UV_PROJECT_ENVIRONMENT: '/mnt/storage12tb/skills/debugger/.venv' },
        })
        state.path = stdout.trim().split('\n').at(-1)
        if (!state.path || !state.path.startsWith(join(workspace, '.vscode/debugger-bridge/') )) throw new Error('Unexpected debugger status path')
        const deadline = Date.now() + 40000
        let receipt: BridgeStatus = { status: 'pending' }
        while (Date.now() < deadline) {
          receipt = JSON.parse(readFileSync(state.path, 'utf8'))
          if (!['pending', 'running', 'starting'].includes(receipt.status)) break
          await new Promise(resolve => setTimeout(resolve, 200))
        }
        if (receipt.sessionState) state.session = receipt.sessionState
        if (['pending', 'starting', 'error'].includes(receipt.status)) { res.statusCode = 409 }
        res.end(JSON.stringify({ status: receipt.status, receipt, session: state.session, proof_path: state.path, mapping: { ...target, file: relative(workspace, target.file) } }))
      } finally { state.busy = false; workspaceBusy = false }
    } catch (error) {
      res.statusCode = 409
      res.end(JSON.stringify({ status: 'unavailable', error: String(error) }))
    }
  }
}
