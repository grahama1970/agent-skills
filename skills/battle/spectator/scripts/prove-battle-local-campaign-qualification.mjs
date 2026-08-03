#!/usr/bin/env node
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const phase = process.env.BATTLE_LOCAL_CAMPAIGN_PHASE ?? 'pause'
const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_LOCAL_CAMPAIGN_PROOF_DIR ?? '/tmp/battle-local-campaign-qualification')
const readyPath = process.env.BATTLE_LIVE_CONTROL_READY
const token = process.env.BATTLE_LIVE_CONTROL_TOKEN ?? 'battle-local-campaign-token'
if (!readyPath) throw new Error('BATTLE_LIVE_CONTROL_READY is required')
const ready = JSON.parse(await readFile(readyPath, 'utf8'))
const liveBase = String(process.env.BATTLE_LIVE_CONTROL_BASE ?? ready.base_url).replace(/\/$/, '')
const liveUrl = `${host}/#battle/live?engine=pixi&battle=battle-004&liveBase=${encodeURIComponent(liveBase)}&controlToken=${encodeURIComponent(token)}&pixiTest=1&reducedMotion=1&particles=0`
const fixtureUrl = `${host}/#battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi&pixiTest=1&reducedMotion=1&particles=0`
const checks = []
const consoleErrors = []

const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${JSON.stringify(detail)}`)
}

async function sha256(path) {
  return createHash('sha256').update(await readFile(path)).digest('hex')
}

async function waitForState(predicate, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  let payload = {}
  while (Date.now() < deadline) {
    try {
      payload = JSON.parse(await readFile(ready.state_path, 'utf8'))
      if (predicate(payload)) return payload
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(`timed out waiting for state predicate; last=${JSON.stringify(payload)}`)
}

async function panelReadback(page, label) {
  const payload = await page.evaluate((name) => {
    const panel = document.querySelector('[data-qid="battle:human-interjection:panel"]')
    const button = document.querySelector('[data-qid="battle:human-interjection:pause-button"]')
    const states = [...document.querySelectorAll('[data-qid^="battle:human-interjection:state:"]')].map((element) => ({
      qid: element.getAttribute('data-qid'),
      status: element.getAttribute('data-status'),
      requestId: element.getAttribute('data-request-id'),
      backendReceipt: element.getAttribute('data-backend-receipt'),
      receiptPath: element.getAttribute('data-receipt-path'),
      text: element.textContent?.replace(/\s+/g, ' ').trim() ?? '',
    }))
    return {
      label: name,
      panel: {
        state: panel?.getAttribute('data-state') ?? null,
        live: panel?.getAttribute('data-live') ?? null,
        mocked: panel?.getAttribute('data-mocked') ?? null,
        runId: panel?.getAttribute('data-run-id') ?? null,
        controlAvailable: panel?.getAttribute('data-control-available') ?? null,
        controlStatus: panel?.getAttribute('data-control-status') ?? null,
        controlRequestId: panel?.getAttribute('data-control-request-id') ?? null,
      },
      button: button ? {
        disabled: button.hasAttribute('disabled'),
        status: button.getAttribute('data-status'),
        requestId: button.getAttribute('data-request-id'),
      } : null,
      states,
      pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    }
  }, label)
  const path = resolve(outDir, `readbacks/${phase}-${label}.json`)
  await writeFile(path, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
  return payload
}

await mkdir(resolve(outDir, 'screenshots'), { recursive: true })
await mkdir(resolve(outDir, 'readbacks'), { recursive: true })

const health = await (await fetch(`${liveBase}/healthz`)).json()
record('health-pass', health.status === 'PASS' && health.control?.available === true, health)

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
page.on('pageerror', (error) => consoleErrors.push(error.message))
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})

const observed = {}
if (phase === 'pause') {
  const beforeRound2 = await waitForState((state) => state.status === 'running' && state.current_round === 1, 60000)
  observed.before_round2 = beforeRound2
  await page.goto(liveUrl, { waitUntil: 'networkidle', timeout: 60000 })
  await page.waitForSelector('[data-qid="battle:human-interjection:pause-button"]', { timeout: 20000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 })
  const initial = await panelReadback(page, 'initial')
  await page.screenshot({ path: resolve(outDir, 'screenshots/pause-01-initial.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
  record('initial-control-enabled', initial.panel.controlAvailable === 'true' && initial.button?.disabled === false, initial)
  record('initial-pixi-route', initial.pixi === 'animated-sprites', initial.pixi)
  await page.click('[data-qid="battle:human-interjection:pause-button"]')
  await page.waitForFunction(() => document.querySelector('[data-qid="battle:human-interjection:panel"]')?.getAttribute('data-control-status') === 'pending', null, { timeout: 5000 })
  const pending = await panelReadback(page, 'pending')
  record('pending-visible', pending.panel.controlStatus === 'pending' && Boolean(pending.panel.controlRequestId), pending)
  await page.waitForFunction(() => (document.querySelector('[data-qid="battle:human-interjection:panel"]')?.getAttribute('data-state') ?? '').includes('accepted'), null, { timeout: 10000 })
  const accepted = await panelReadback(page, 'accepted')
  record('accepted-visible', accepted.states.some((state) => state.status === 'ACCEPTED' && state.backendReceipt === 'true'), accepted)
  await page.waitForFunction(() => (document.querySelector('[data-qid="battle:human-interjection:panel"]')?.getAttribute('data-state') ?? '').includes('applied'), null, { timeout: 45000 })
  const applied = await panelReadback(page, 'applied')
  await page.screenshot({ path: resolve(outDir, 'screenshots/pause-02-applied.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
  record('applied-visible', applied.states.some((state) => state.status === 'APPLIED' && state.backendReceipt === 'true'), applied)
  const paused = await waitForState((state) => state.status === 'paused' && state.current_round === 2, 30000)
  observed.paused = paused
  const wrongRun = await fetch(`${liveBase}${ready.control_endpoint}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'pause_after_round', run_id: 'wrong-run', request_id: 'wrong-run-proof', boundary: 'round_running' }),
  })
  const badAuth = await fetch(`${liveBase}${ready.control_endpoint}`, {
    method: 'POST',
    headers: { Authorization: 'Bearer wrong-token', 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'pause_after_round', run_id: ready.run_id, request_id: 'bad-auth-proof', boundary: 'round_running' }),
  })
  const malformed = await fetch(`${liveBase}${ready.control_endpoint}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'pause_after_round', run_id: ready.run_id, request_id: 'malformed-proof' }),
  })
  const duplicate = await fetch(`${liveBase}${ready.control_endpoint}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'pause_after_round', run_id: ready.run_id, request_id: pending.panel.controlRequestId, boundary: 'round_running' }),
  })
  const duplicateBody = await duplicate.json()
  record('wrong-run-fails-closed', wrongRun.status === 403, wrongRun.status)
  record('bad-auth-fails-closed', badAuth.status === 403, badAuth.status)
  record('malformed-fails-closed', malformed.status === 403, malformed.status)
  record('duplicate-idempotent', duplicate.status === 200 && duplicateBody.status === 'DUPLICATE_ACCEPTED', duplicateBody)
  observed.no_round3_before_resume = !(await stat(resolve(outDir, 'worker-starts/round-0003-red-proactive.json')).then(() => true).catch(() => false))
  record('no-round3-before-resume', observed.no_round3_before_resume, observed.no_round3_before_resume)
} else if (phase === 'reconnect') {
  const completed = await waitForState((state) => state.status === 'completed' && state.current_round === 3, 60000)
  observed.completed = completed
  await page.goto(liveUrl, { waitUntil: 'networkidle', timeout: 60000 })
  await page.waitForSelector('[data-qid="battle:human-interjection:panel"][data-state*="applied"]', { timeout: 20000 })
  const reconnected = await panelReadback(page, 'reconnected')
  await page.screenshot({ path: resolve(outDir, 'screenshots/reconnect-01-applied.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
  record('reconnect-applied-visible', reconnected.states.some((state) => state.status === 'APPLIED' && state.backendReceipt === 'true'), reconnected)
  const snapshot = await (await fetch(`${liveBase}${ready.snapshot_endpoint}`)).json()
  record('snapshot-same-run', snapshot.run_id === ready.run_id && snapshot.human_interjection_panel?.run_id === ready.run_id, snapshot)
  await page.goto(fixtureUrl, { waitUntil: 'networkidle', timeout: 60000 })
  await page.waitForSelector('[data-qid="battle:human-interjection:panel"]', { timeout: 20000 })
  const fixture = await panelReadback(page, 'fixture')
  await page.screenshot({ path: resolve(outDir, 'screenshots/reconnect-02-fixture.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
  observed.fixture_route_has_no_button = fixture.button === null && fixture.panel.controlAvailable === 'false'
  record('fixture-route-has-no-button', observed.fixture_route_has_no_button, fixture)
} else {
  throw new Error(`unsupported phase: ${phase}`)
}

record('browser-console-clean', consoleErrors.length === 0, consoleErrors)
await browser.close()

const failed = checks.filter((item) => !item.pass)
const report = {
  schema: `battle.local_campaign_browser_${phase}.v1`,
  status: failed.length === 0 ? 'PASS' : 'FAIL',
  mocked: false,
  live: true,
  phase,
  host,
  liveBase,
  ready,
  checks,
  failed: failed.map((item) => item.id),
  observed,
  proof_sha256: await sha256(readyPath),
}
await writeFile(resolve(outDir, `browser-${phase}-proof.json`), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(report, null, 2))
if (failed.length) process.exit(1)
