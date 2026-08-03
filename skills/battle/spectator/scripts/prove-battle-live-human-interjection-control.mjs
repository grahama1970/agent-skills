#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import { relative, resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_LIVE_HUMAN_INTERJECTION_CONTROL_PROOF_DIR ?? '/tmp/battle-live-human-interjection-control-proof')
const readyPath = process.env.BATTLE_LIVE_CONTROL_READY
if (!readyPath) throw new Error('BATTLE_LIVE_CONTROL_READY is required')
const ready = JSON.parse(await readFile(readyPath, 'utf8'))
const liveBase = String(process.env.BATTLE_LIVE_CONTROL_BASE ?? ready.base_url).replace(/\/$/, '')
const token = process.env.BATTLE_LIVE_CONTROL_TOKEN ?? 'battle-live-control-proof-token'
const screenshotsDir = resolve(outDir, 'screenshots')
const readbacksDir = resolve(outDir, 'readbacks')
const spectatorDir = resolve(import.meta.dirname, '..')
const battleDir = resolve(spectatorDir, '..')
const repositoryDir = resolve(battleDir, '..', '..')
const liveUrl = `${host}/#battle/live?engine=pixi&battle=battle-004&liveBase=${encodeURIComponent(liveBase)}&controlToken=${encodeURIComponent(token)}&pixiTest=1&reducedMotion=1&particles=0`
const fixtureUrl = `${host}/#battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi&pixiTest=1&reducedMotion=1&particles=0`
const checks = []
const errors = []

const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${JSON.stringify(detail)}`)
}

async function sha256File(path) {
  return createHash('sha256').update(await readFile(path)).digest('hex')
}

async function artifact(path, id, root = outDir) {
  const fileStat = await stat(path)
  return { id, path: relative(root, path), sha256: await sha256File(path), bytes: fileStat.size }
}

async function panelReadback(page, label) {
  const readback = await page.evaluate((name) => {
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
        sourceBound: panel?.getAttribute('data-source-bound') ?? null,
        live: panel?.getAttribute('data-live') ?? null,
        mocked: panel?.getAttribute('data-mocked') ?? null,
        runId: panel?.getAttribute('data-run-id') ?? null,
        controlAvailable: panel?.getAttribute('data-control-available') ?? null,
        controlStatus: panel?.getAttribute('data-control-status') ?? null,
        controlRequestId: panel?.getAttribute('data-control-request-id') ?? null,
        text: panel?.textContent?.replace(/\s+/g, ' ').trim() ?? null,
      },
      button: button ? {
        disabled: button.hasAttribute('disabled'),
        status: button.getAttribute('data-status'),
        requestId: button.getAttribute('data-request-id'),
        text: button.textContent?.replace(/\s+/g, ' ').trim() ?? '',
      } : null,
      states,
      pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    }
  }, label)
  const readbackPath = resolve(readbacksDir, `${label}.json`)
  await writeFile(readbackPath, `${JSON.stringify(readback, null, 2)}\n`, 'utf8')
  return { ...readback, readback: relative(outDir, readbackPath) }
}

await mkdir(screenshotsDir, { recursive: true })
await mkdir(readbacksDir, { recursive: true })

const health = await (await fetch(`${liveBase}/healthz`)).json()
record('adapter-health-pass', health.schema === 'battle.live_transport_health.v1' && health.status === 'PASS', health)
record('control-health-available', health.control?.available === true && health.control?.endpoint === ready.control_endpoint, health.control)

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(message.text())
})

await page.goto(liveUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:human-interjection:panel"]', { timeout: 20_000 })
await page.waitForSelector('[data-qid="battle:human-interjection:pause-button"]', { timeout: 20_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
const initial = await panelReadback(page, '01-initial')
await page.screenshot({ path: resolve(screenshotsDir, '01-initial.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
record('initial-live-control-enabled', initial.panel.controlAvailable === 'true' && initial.button?.disabled === false, initial)
record('initial-pixi-route', initial.pixi === 'animated-sprites', initial.pixi)

await page.click('[data-qid="battle:human-interjection:pause-button"]')
await page.waitForFunction(() => {
  const panel = document.querySelector('[data-qid="battle:human-interjection:panel"]')
  return panel?.getAttribute('data-control-status') === 'pending' || (panel?.getAttribute('data-state') ?? '').includes('pending')
}, null, { timeout: 5000 })
const pending = await panelReadback(page, '02-pending')
await page.screenshot({ path: resolve(screenshotsDir, '02-pending.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
record('pending-visible-with-request-id', pending.panel.controlStatus === 'pending' && Boolean(pending.panel.controlRequestId), pending.panel)

await page.waitForFunction(() => {
  const panel = document.querySelector('[data-qid="battle:human-interjection:panel"]')
  return (panel?.getAttribute('data-state') ?? '').includes('accepted')
}, null, { timeout: 10_000 })
const accepted = await panelReadback(page, '03-accepted')
await page.screenshot({ path: resolve(screenshotsDir, '03-accepted.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
record('accepted-backend-receipt-visible', accepted.states.some((state) => state.status === 'ACCEPTED' && state.backendReceipt === 'true'), accepted.states)
record('accepted-button-disabled', accepted.button?.disabled === true, accepted.button)

await page.waitForFunction(() => {
  const panel = document.querySelector('[data-qid="battle:human-interjection:panel"]')
  return (panel?.getAttribute('data-state') ?? '').includes('applied')
}, null, { timeout: 30_000 })
const applied = await panelReadback(page, '04-applied')
await page.screenshot({ path: resolve(screenshotsDir, '04-applied.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
record('applied-backend-receipt-visible', applied.states.some((state) => state.status === 'APPLIED' && state.backendReceipt === 'true'), applied.states)

await page.reload({ waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:human-interjection:panel"][data-state*="applied"]', { timeout: 20_000 })
const refreshed = await panelReadback(page, '05-refresh-applied')
await page.screenshot({ path: resolve(screenshotsDir, '05-refresh-applied.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
record('refresh-retains-applied', refreshed.panel.state?.includes('applied'), refreshed.panel)

const wrongRun = await fetch(`${liveBase}${ready.control_endpoint}`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'application/json' },
  body: JSON.stringify({ action: 'pause_after_round', run_id: 'wrong-run', request_id: 'wrong-run-proof', boundary: 'round_running' }),
})
record('wrong-run-fails-closed', wrongRun.status === 403, String(wrongRun.status))
const badAuth = await fetch(`${liveBase}${ready.control_endpoint}`, {
  method: 'POST',
  headers: { Authorization: 'Bearer wrong-token', 'Content-Type': 'application/json', Accept: 'application/json' },
  body: JSON.stringify({ action: 'pause_after_round', run_id: ready.run_id, request_id: 'bad-auth-proof', boundary: 'round_running' }),
})
record('bad-auth-fails-closed', badAuth.status === 403, String(badAuth.status))
const malformed = await fetch(`${liveBase}${ready.control_endpoint}`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'application/json' },
  body: JSON.stringify({ action: 'pause_after_round', run_id: ready.run_id, request_id: 'malformed-proof' }),
})
record('malformed-boundary-fails-closed', malformed.status === 403, String(malformed.status))
const duplicate = await fetch(`${liveBase}${ready.control_endpoint}`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'application/json' },
  body: JSON.stringify({ action: 'pause_after_round', run_id: ready.run_id, request_id: pending.panel.controlRequestId, boundary: 'round_running' }),
})
const duplicateBody = await duplicate.json()
record('duplicate-reuses-request-id', duplicate.status === 200 && duplicateBody.status === 'DUPLICATE_ACCEPTED', duplicateBody)

await page.goto(fixtureUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:human-interjection:panel"]', { timeout: 20_000 })
const fixture = await panelReadback(page, '06-fixture-no-control')
await page.screenshot({ path: resolve(screenshotsDir, '06-fixture-no-control.png'), fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
record('fixture-route-has-no-live-button', fixture.button === null && fixture.panel.controlAvailable === 'false', fixture)

const statePayload = JSON.parse(await readFile(ready.state_path, 'utf8'))
record('actual-battle-state-paused', statePayload.status === 'paused' && statePayload.current_round === 1, statePayload)
record('browser-console-clean', errors.length === 0, errors)

await browser.close()

const failed = checks.filter((item) => !item.pass)
const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repositoryDir, encoding: 'utf8' }).trim()
const report = {
  schema: 'battle.live_human_interjection_control_proof.v1',
  status: failed.length === 0 ? 'PASS' : 'FAIL',
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  liveBase,
  ready,
  checks,
  failed: failed.map((item) => item.id),
  readbacks: [
    initial.readback,
    pending.readback,
    accepted.readback,
    applied.readback,
    refreshed.readback,
    fixture.readback,
  ],
  screenshots: [
    'screenshots/01-initial.png',
    'screenshots/02-pending.png',
    'screenshots/03-accepted.png',
    'screenshots/04-applied.png',
    'screenshots/05-refresh-applied.png',
    'screenshots/06-fixture-no-control.png',
  ],
  observed: {
    request_id: pending.panel.controlRequestId,
    backend_accepted_visible: accepted.states.some((state) => state.status === 'ACCEPTED'),
    backend_applied_visible: applied.states.some((state) => state.status === 'APPLIED'),
    durable_state: statePayload.status,
    current_round: statePayload.current_round,
  },
  claims: {
    proves: [
      'The canonical Pixi live route enabled pause_after_round only against a live local adapter with control capability.',
      'A browser click submitted one authenticated pause_after_round request id to the backend.',
      'The UI showed pending, then backend ACCEPTED, then backend APPLIED receipt state.',
      'The ordinary Battle run loop paused durable state at round 1 after the current round completed.',
      'A browser refresh reconstructed APPLIED from backend snapshot receipts.',
      'Wrong run, bad auth, malformed boundary, duplicate request id, and fixture route cases failed closed.',
    ],
    does_not_prove: [
      'Production identity, CSRF, OAuth, TLS, DNS, ingress, or tenant authorization.',
      'External staging readiness.',
    ],
  },
}
await writeFile(resolve(outDir, 'proof.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
const proofArtifacts = await Promise.all([
  artifact(resolve(outDir, 'proof.json'), 'proof.json'),
  ...report.screenshots.map((item) => artifact(resolve(outDir, item), item)),
  ...report.readbacks.map((item) => artifact(resolve(outDir, item), item)),
])
await writeFile(resolve(outDir, 'proof-manifest.json'), `${JSON.stringify({
  schema: 'battle.live_human_interjection_control_proof_manifest.v1',
  status: report.status,
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  proof_artifacts: proofArtifacts,
  claims: report.claims,
}, null, 2)}\n`, 'utf8')

console.log(JSON.stringify(report, null, 2))
if (failed.length) process.exit(1)
console.log('BATTLE_LIVE_HUMAN_INTERJECTION_CONTROL_PROOF_PASS')
