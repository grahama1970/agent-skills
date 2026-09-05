import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { join, relative, isAbsolute, sep } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { deckContext, type DeckContext } from './deck-context'

const exec = promisify(execFile)
interface Mapping { file: string; line: number; launch?: string; locals?: string[] }
interface Session { vscodeSessionId: string; stopSequence: number; selectedThreadId?: number }
interface BridgeStatus { id?: string; status: string; proofValid?: boolean; sessionState?: Session; [key: string]: unknown }
const states = new Map<string, { path?: string; session?: Session; busy: boolean }>()
let workspaceBusy = false

function mapping(context: DeckContext, workspace: string, slide: string): Mapping | null {
  if (!context.deck.slides.some(s => s.id === slide && !s.hidden)) throw new Error('Slide not in active deck')
  const path = join(context.directory, 'debugger.json')
  if (!existsSync(path)) return null
  const config = JSON.parse(readFileSync(path, 'utf8'))
  if (config.schema !== 'pitchdeck.debugger_map.v1') throw new Error('Invalid debugger map schema')
  const item: Mapping = config.slides?.[slide]
  if (!item) return null
  if (typeof item.file !== 'string' || isAbsolute(item.file)) throw new Error('Mapped file must be workspace-relative')
  const file = realpathSync(join(workspace, item.file))
  const rel = relative(workspace, file)
  if (rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) throw new Error('Mapped file escapes approved workspace')
  if (!Number.isSafeInteger(item.line) || item.line < 1 || item.line > readFileSync(file, 'utf8').split('\n').length) throw new Error('Invalid mapped line')
  if (item.locals && (!Array.isArray(item.locals) || item.locals.length > 20 || item.locals.some(n => typeof n !== 'string' || !/^[\w]+$/.test(n)))) throw new Error('Invalid local variable names')
  return { ...item, file }
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
        const target = mapping(context, workspace, slide)
        const receipt: BridgeStatus | null = state.path && existsSync(state.path) ? JSON.parse(readFileSync(state.path, 'utf8')) : null
        if (receipt?.sessionState) state.session = receipt.sessionState
        res.end(JSON.stringify({ mapping: target && { ...target, file: relative(workspace, target.file) }, workspace, receipt, session: state.session, busy: state.busy, status: !target ? 'unmapped' : receipt?.status || 'not-connected' }))
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
      const target = mapping(context, workspace, request.slide_id)
      if (!target) throw new Error('No debugger mapping for this slide; configure debugger.json beside the emitted deck')
      const args = ['--workspace', workspace, '--workspace-artifacts', '--expect-extension-host-kind', process.env.PITCHDECK_DEBUG_HOST_KIND || 'ui', '--action', request.action, '--no-save-before-start']
      if (request.action === 'reveal') args.push('--reveal', `${target.file}:${target.line}:1:${target.line}:1`)
      else if (request.action === 'start') {
        if (!target.launch || typeof target.launch !== 'string') throw new Error('Slide has no launch configuration')
        args.push('--launch-config-name', target.launch, '--break', `${target.file}:${target.line}`)
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
