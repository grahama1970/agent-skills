#!/usr/bin/env node
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_LIVE_TRANSPORT_PROOF_DIR ?? '/tmp/battle-pr8-live-transport-proof')
let liveBase = (process.env.BATTLE_LIVE_TRANSPORT_BASE ?? 'http://127.0.0.1:18765').replace(/\/$/, '')
let liveAdapterProcess = null

async function freePort() {
  return await new Promise((resolvePort, rejectPort) => {
    const server = createServer()
    server.on('error', rejectPort)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : null
      server.close(() => {
        if (port) resolvePort(port)
        else rejectPort(new Error('failed to allocate a loopback port'))
      })
    })
  })
}

async function liveAdapterHealthy(base) {
  try {
    const response = await fetch(`${base}/healthz`, { signal: AbortSignal.timeout(800) })
    if (!response.ok) return false
    const health = await response.json()
    return health.schema === 'battle.live_transport_health.v1' && health.status === 'PASS'
  } catch {
    return false
  }
}

function stopLiveAdapter() {
  if (liveAdapterProcess && !liveAdapterProcess.killed) {
    liveAdapterProcess.kill('SIGTERM')
  }
}

async function ensureLiveAdapter() {
  if (await liveAdapterHealthy(liveBase)) return liveBase
  if (process.env.BATTLE_LIVE_TRANSPORT_BASE) return liveBase

  const httpPort = await freePort()
  const websocketPort = await freePort()
  liveBase = `http://127.0.0.1:${httpPort}`
  liveAdapterProcess = spawn(
    './run.sh',
    [
      'serve-live-transport',
      '--port',
      String(httpPort),
      '--websocket-port',
      String(websocketPort),
      '--fixture',
      'spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json',
    ],
    {
      cwd: resolve(process.cwd(), '..'),
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  let stderr = ''
  liveAdapterProcess.stderr.on('data', (chunk) => {
    stderr += chunk.toString()
  })
  process.on('exit', stopLiveAdapter)
  process.on('SIGINT', () => {
    stopLiveAdapter()
    process.exit(130)
  })
  process.on('SIGTERM', () => {
    stopLiveAdapter()
    process.exit(143)
  })

  const deadline = Date.now() + 15_000
  while (Date.now() < deadline) {
    if (liveAdapterProcess.exitCode !== null) {
      throw new Error(`serve-live-transport exited early with ${liveAdapterProcess.exitCode}: ${stderr.slice(-1000)}`)
    }
    if (await liveAdapterHealthy(liveBase)) return liveBase
    await new Promise((resolveTimer) => setTimeout(resolveTimer, 200))
  }
  throw new Error(`serve-live-transport did not become healthy at ${liveBase}: ${stderr.slice(-1000)}`)
}

await ensureLiveAdapter()
const liveUrl = `${host}/#battle/live?engine=pixi&battle=battle-004&liveBase=${encodeURIComponent(liveBase)}`
const contractOnlyUrl = `${host}/#battle/live?engine=pixi&battle=battle-004&liveBase=${encodeURIComponent('http://127.0.0.1:59999')}`
const fileBackedUrl = `${host}/#battle/live?engine=pixi&fixture=battle-004-parent-spawn`
const invalidUrl = `${host}/#battle/live?engine=pixi&battle=not-a-battle`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

await mkdir(outDir, { recursive: true })

const contractJson = await (await fetch(`${host}/battle-fixtures/battle-004-pr8-live-transport/battle.live_transport_contract.json`)).json()
record('1-contract-schema', contractJson.schema === 'battle.live_transport_contract.v1', contractJson.schema)
record('2-contract-published', contractJson.live === 'contract_only' && contractJson.mocked === false, JSON.stringify({ live: contractJson.live, mocked: contractJson.mocked }))
record('3-sse-shape', contractJson.transport?.kind === 'sse' && contractJson.transport?.content_type === 'text/event-stream', JSON.stringify(contractJson.transport))
record('4-genetic-16', contractJson.event_stream?.genetic_event_types_when_live?.length === 16, String(contractJson.event_stream?.genetic_event_types_when_live?.length))
record(
  '5-snapshot-endpoint',
  contractJson.initial_snapshot?.endpoint === '/battle/live/battle-004/snapshot',
  contractJson.initial_snapshot?.endpoint,
)

const health = await (await fetch(`${liveBase}/healthz`)).json()
record('6-adapter-health', health.schema === 'battle.live_transport_health.v1' && health.status === 'PASS', JSON.stringify(health))
const snapshot = await (await fetch(`${liveBase}/battle/live/battle-004/snapshot`)).json()
record('7-adapter-snapshot', snapshot.schema === 'battle.snapshot.v1' && snapshot.last_seq === 36, JSON.stringify({ schema: snapshot.schema, last_seq: snapshot.last_seq }))

const sseText = await (await fetch(`${liveBase}/battle/live/battle-004/events`, { headers: { Accept: 'text/event-stream' } })).text()
const sseEvents = sseText
  .split('\n\n')
  .map((frame) => frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n'))
  .filter(Boolean)
  .map((data) => JSON.parse(data))
record('8-adapter-sse-count', sseEvents.length === 36 && sseEvents[0]?.schema === 'battle.live_event.v1', String(sseEvents.length))
const resumed = await fetch(`${liveBase}/battle/live/battle-004/events`, {
  headers: { Accept: 'text/event-stream', 'Last-Event-ID': '2' },
})
const resumedText = await resumed.text()
const resumedEvents = resumedText
  .split('\n\n')
  .map((frame) => frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n'))
  .filter(Boolean)
  .map((data) => JSON.parse(data))
record('9-adapter-resume', resumedEvents.length === 34 && resumedEvents[0]?.seq === 3, String(resumedEvents.length))
const future = await fetch(`${liveBase}/battle/live/battle-004/events`, {
  headers: { Accept: 'text/event-stream', 'Last-Event-ID': '999' },
})
record('10-adapter-future-fail-closed', future.status === 400, String(future.status))

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (msg) => {
  if (msg.type() !== 'error') return
  const text = msg.text()
  // Expected when probing the intentional dead liveBase fallback.
  if (/ERR_CONNECTION_REFUSED|Failed to fetch|NetworkError|load resource/i.test(text) && /59999|liveBase/i.test(text + liveBase)) {
    return
  }
  if (/ERR_CONNECTION_REFUSED|Failed to load resource: net::ERR_CONNECTION_REFUSED/i.test(text)) {
    return
  }
  errors.push(text)
})

await page.goto(liveUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:banner"]', { timeout: 20_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForFunction(() => {
  const seq = document.querySelector('[data-qid="battle:live:seq"]')?.textContent ?? ''
  return /36\/36/.test(seq) || /seq 36\//.test(seq)
}, { timeout: 20_000 })
await page.waitForTimeout(800)

const liveChrome = await page.evaluate(() => {
  const text = document.body.textContent ?? ''
  return {
    banner: !!document.querySelector('[data-qid="battle:live:banner"]'),
    mode: document.querySelector('[data-qid="battle:live:banner:mode"]')?.textContent ?? '',
    liveSource: document.querySelector('[data-qid="battle:live:banner:live-source"]')?.textContent ?? '',
    connected: document.querySelector('[data-qid="battle:live:banner:sse-connected"]')?.textContent ?? '',
    transportMode: document.querySelector('[data-qid="battle:live:banner:transport-mode"]')?.textContent ?? '',
    mocked: document.querySelector('[data-qid="battle:live:banner:mocked"]')?.textContent ?? '',
    seq: document.querySelector('[data-qid="battle:live:seq"]')?.textContent ?? '',
    sseClient: document.querySelector('[data-qid="battle:live:sse-client"]')?.textContent ?? '',
    baseUrl: document.querySelector('[data-qid="battle:live:base-url"]')?.textContent ?? '',
    geneticCount: document.querySelector('[data-qid="battle:live:genetic-count"]')?.textContent ?? '',
    may: document.querySelector('[data-qid="battle:live:claim-may"]')?.textContent ?? '',
    mustNot: document.querySelector('[data-qid="battle:live:claim-must-not"]')?.textContent ?? '',
    geneticTypes: [...document.querySelectorAll('[data-qid^="battle:live:genetic:"]')].map((el) => el.getAttribute('data-qid')),
    nav: !!document.querySelector('[data-qid="battle:nav:live"]'),
    pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    geneticBanner: !!document.querySelector('[data-qid="battle:genetic:banner"]'),
    text,
  }
})

record('11-live-banner', liveChrome.banner, 'banner')
record('12-live-mode-badge', /LIVE SSE ADAPTER/i.test(liveChrome.mode), liveChrome.mode)
record('13-live-source-badge', /LOCAL HTTP SSE/i.test(liveChrome.liveSource), liveChrome.liveSource)
record('14-sse-connected-badge', /EVENTSOURCE OPEN|SSE CONNECTED/i.test(liveChrome.connected), liveChrome.connected)
record('14b-eventsource-mode', /TRANSPORT:\s*EVENTSOURCE/i.test(liveChrome.transportMode), liveChrome.transportMode)
record('15-mocked-no', /MOCKED:\s*NO/i.test(liveChrome.mocked), liveChrome.mocked)
record('16-seq-complete', /36\/36/.test(liveChrome.seq), liveChrome.seq)
record('17-sse-client-open-or-ended', /(open|ended)/i.test(liveChrome.sseClient), liveChrome.sseClient)
record('18-base-url', liveChrome.baseUrl.includes(liveBase), liveChrome.baseUrl)
record('19-genetic-count', /genetic types\s+16/i.test(liveChrome.geneticCount), liveChrome.geneticCount)
record('20-may-local-sse', /local http sse adapter executed/i.test(liveChrome.may), liveChrome.may.slice(0, 200))
record('21-must-not-production', /production deployment/i.test(liveChrome.mustNot), liveChrome.mustNot.slice(0, 200))
record('22-genetic-types-rendered', liveChrome.geneticTypes.includes('battle:live:genetic:research_started'), JSON.stringify(liveChrome.geneticTypes.slice(0, 5)))
record('23-pixi-backdrop', liveChrome.pixi === 'animated-sprites', liveChrome.pixi)
record('24-genetic-companion-banner', liveChrome.geneticBanner, 'genetic banner')
record('25-nav-live', liveChrome.nav, 'nav')
record(
  '26-no-raw-paths',
  !liveChrome.text.includes('tau-dag-run/') && !liveChrome.text.includes('command-loop/command-artifacts'),
  'paths',
)

await page.screenshot({ path: resolve(outDir, '01-live-sse-adapter.png'), fullPage: true })

await page.goto(contractOnlyUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:banner"]', { timeout: 20_000 })
const blocked = await page.evaluate(() => ({
  mode: document.querySelector('[data-qid="battle:live:banner:mode"]')?.textContent ?? '',
  contractOnly: document.querySelector('[data-qid="battle:live:banner:contract-only"]')?.textContent ?? '',
  noEndpoint: document.querySelector('[data-qid="battle:live:banner:no-endpoint"]')?.textContent ?? '',
  sseClient: document.querySelector('[data-qid="battle:live:sse-client"]')?.textContent ?? '',
}))
record('27-fallback-contract-only', /LIVE CONTRACT/i.test(blocked.mode) && /CONTRACT ONLY/i.test(blocked.contractOnly), JSON.stringify(blocked))
record('28-fallback-not-executed', /NOT EXECUTED/i.test(blocked.noEndpoint), blocked.noEndpoint)
record('29-fallback-client-blocked', /contract_only_blocked/i.test(blocked.sseClient), blocked.sseClient)

await page.goto(fileBackedUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:banner"]', { timeout: 20_000 })
const fileBacked = await page.evaluate(() => ({
  mode: document.querySelector('[data-qid="battle:live:banner:mode"]')?.textContent ?? '',
  seq: document.querySelector('[data-qid="battle:live:seq"]')?.textContent ?? '',
}))
record('30-file-backed-still-works', /FILE-BACKED STREAM/i.test(fileBacked.mode) && /24\/24/.test(fileBacked.seq), JSON.stringify(fileBacked))

await page.goto(invalidUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:blocked"]', { timeout: 20_000 })
const invalid = await page.evaluate(() => document.querySelector('[data-qid="battle:live:blocked"]')?.textContent ?? '')
record('31-unknown-battle-fail-closed', /UNSUPPORTED/i.test(invalid), invalid)

record('32-no-page-errors', errors.length === 0, JSON.stringify(errors.slice(0, 5)))

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify(
    {
      host,
      liveBase,
      liveUrl,
      mocked: false,
      live: 'local_http_sse_adapter',
      checks,
      failed: failed.map((item) => item.id),
    },
    null,
    2,
  ),
)
await browser.close()
stopLiveAdapter()
if (failed.length) {
  console.error(`prove-battle-pr8-live-transport failed: ${failed.map((item) => item.id).join(', ')}`)
  process.exit(1)
}
console.log(`prove-battle-pr8-live-transport passed ${checks.length}/${checks.length}`)
