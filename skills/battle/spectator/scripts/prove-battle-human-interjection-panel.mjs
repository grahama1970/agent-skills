#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import { relative, resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_HUMAN_INTERJECTION_SPECTATOR_PROOF_DIR ?? '/tmp/battle-human-interjection-spectator-proof')
const screenshotsDir = resolve(outDir, 'screenshots')
const readbacksDir = resolve(outDir, 'readbacks')
const spectatorDir = resolve(import.meta.dirname, '..')
const battleDir = resolve(spectatorDir, '..')
const repositoryDir = resolve(battleDir, '..', '..')
const errors = []
const checks = []

const cases = [
  { state: 'pending', fixture: 'battle-004-pause-after-round-pending', qid: 'battle:human-interjection:state:pending', screenshot: '01-pending.png' },
  { state: 'accepted', fixture: 'battle-004-pause-after-round-accepted', qid: 'battle:human-interjection:state:accepted', screenshot: '02-accepted.png' },
  { state: 'applied', fixture: 'battle-004-pause-after-round-applied', qid: 'battle:human-interjection:state:applied', screenshot: '03-applied.png' },
  { state: 'rejected', fixture: 'battle-004-pause-after-round-rejected', qid: 'battle:human-interjection:state:rejected', screenshot: '04-rejected.png' },
  { state: 'unavailable', fixture: 'battle-004-pause-after-round-unavailable', qid: 'battle:human-interjection:state:unavailable', screenshot: '05-unavailable.png' },
  { state: 'missing_backend', fixture: 'battle-004-pause-after-round-missing-backend', qid: 'battle:human-interjection:state:missing_backend', screenshot: '06-missing-backend.png' },
]

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

await mkdir(screenshotsDir, { recursive: true })
await mkdir(readbacksDir, { recursive: true })

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(message.text())
})

async function inspect(item) {
  const url = `${host}/#battle/receipt?engine=pixi&fixture=${item.fixture}&pixiTest=1&reducedMotion=1&particles=0`
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-qid="battle:human-interjection:panel"]', { timeout: 20_000 })
  await page.waitForSelector('[data-qid="battle:race:source"]', { timeout: 20_000 })
  await page.waitForTimeout(500)
  const screenshot = resolve(screenshotsDir, item.screenshot)
  await page.screenshot({ path: screenshot, fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
  const readback = await page.evaluate((expected) => {
    const root = document.querySelector('[data-qid="battle:human-interjection:panel"]')
    const state = document.querySelector(`[data-qid="${expected.qid}"]`)
    const race = document.querySelector('[data-qid="battle:race:source"]')
    const body = document.body.textContent?.replace(/\s+/g, ' ').trim() ?? ''
    return {
      fixture: expected.fixture,
      expectedState: expected.state,
      panel: {
        state: root?.getAttribute('data-state') ?? null,
        sourceBound: root?.getAttribute('data-source-bound') ?? null,
        live: root?.getAttribute('data-live') ?? null,
        mocked: root?.getAttribute('data-mocked') ?? null,
        runId: root?.getAttribute('data-run-id') ?? null,
        sourceProofReceipt: root?.getAttribute('data-source-proof-receipt') ?? null,
        text: root?.textContent?.replace(/\s+/g, ' ').trim() ?? null,
      },
      state: {
        found: Boolean(state),
        status: state?.getAttribute('data-status') ?? null,
        requestId: state?.getAttribute('data-request-id') ?? null,
        reasonCode: state?.getAttribute('data-reason-code') ?? null,
        backendReceipt: state?.getAttribute('data-backend-receipt') ?? null,
        receiptPath: state?.getAttribute('data-receipt-path') ?? null,
        text: state?.textContent?.replace(/\s+/g, ' ').trim() ?? null,
      },
      race: {
        battleId: race?.getAttribute('data-battle-id') ?? null,
        sourceProofId: race?.getAttribute('data-source-proof-id') ?? null,
      },
      bodyHasLocalPreview: /local preview|mock preview|design fixture/i.test(body),
    }
  }, item)
  const readbackPath = resolve(readbacksDir, `${item.fixture}.json`)
  await writeFile(readbackPath, `${JSON.stringify(readback, null, 2)}\n`, 'utf8')
  return { ...readback, url, screenshot: relative(outDir, screenshot), readback: relative(outDir, readbackPath) }
}

const states = []
for (const item of cases) {
  states.push(await inspect(item))
}

for (const state of states) {
  const expectedMissing = state.expectedState === 'missing_backend'
  record(`${state.expectedState}-panel-present`, Boolean(state.panel.state), state)
  record(`${state.expectedState}-state-visible`, state.state.found, state.state)
  record(`${state.expectedState}-state-declared`, state.panel.state?.includes(state.expectedState), state.panel)
  record(`${state.expectedState}-live-not-mocked`, state.panel.mocked === 'false' && (state.panel.live === 'true' || expectedMissing), state.panel)
  record(`${state.expectedState}-source-boundary`, expectedMissing ? state.panel.sourceBound === 'false' : state.panel.sourceBound === 'true', state.panel)
  record(`${state.expectedState}-no-local-preview-copy`, !state.bodyHasLocalPreview, state.panel.text)
}
record('browser-console-clean', errors.length === 0, errors)

await browser.close()

const failed = checks.filter((check) => !check.pass)
const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repositoryDir, encoding: 'utf8' }).trim()
const report = {
  schema: 'battle.human_interjection_spectator_proof.v1',
  status: failed.length === 0 ? 'PASS' : 'FAIL',
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  checks,
  failed: failed.map((check) => check.id),
  states,
  screenshots: cases.map((item) => `screenshots/${item.screenshot}`),
  readbacks: cases.map((item) => `readbacks/${item.fixture}.json`),
  claims: {
    proves: [
      'The canonical Pixi receipt route renders pause_after_round pending, accepted, applied, rejected, and unavailable states from generated backend receipt fields.',
      'The canonical Pixi receipt route fails closed to missing_backend when pause_after_round backend fields are absent.',
    ],
    does_not_prove: [
      'Tau execution pausing beyond the backend after-round application receipt.',
      'Production auth, websocket fanout, or staging infrastructure readiness.',
    ],
  },
}

await writeFile(resolve(outDir, 'proof.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
const proofArtifacts = await Promise.all([
  artifact(resolve(outDir, 'proof.json'), 'proof.json'),
  ...cases.map((item) => artifact(resolve(screenshotsDir, item.screenshot), `screenshots/${item.screenshot}`)),
  ...cases.map((item) => artifact(resolve(readbacksDir, `${item.fixture}.json`), `readbacks/${item.fixture}.json`)),
])
await writeFile(resolve(outDir, 'proof-manifest.json'), `${JSON.stringify({
  schema: 'battle.human_interjection_spectator_proof_manifest.v1',
  status: report.status,
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  proof_artifacts: proofArtifacts,
  claims: report.claims,
}, null, 2)}\n`, 'utf8')

console.log(JSON.stringify(report, null, 2))
if (failed.length) process.exit(1)
console.log('BATTLE_PROVE_HUMAN_INTERJECTION_SPECTATOR_PASS')
