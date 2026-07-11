#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_LIVE_TRANSPORT_PROOF_DIR ?? '/tmp/battle-pr8-live-transport-proof')
const url = `${host}/#battle/live?engine=pixi&fixture=battle-004-parent-spawn`
const invalidUrl = `${host}/#battle/live?engine=pixi&fixture=not-a-registered-stream`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

await mkdir(outDir, { recursive: true })
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})

const streamBase = `${host}/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream`
const manifest = await (await fetch(`${streamBase}/manifest.json`)).json()
const snapshot = await (await fetch(`${streamBase}/latest-snapshot.json`)).json()
const eventsText = await (await fetch(`${streamBase}/events.jsonl`)).text()
const events = eventsText
  .split('\n')
  .map((line) => line.trim())
  .filter(Boolean)
  .map((line) => JSON.parse(line))
const stream = {
  manifestSchema: manifest.schema,
  mode: manifest.mode,
  mocked: manifest.mocked,
  eventCount: manifest.event_count,
  lastSeq: manifest.last_seq,
  transport: manifest.stream_contract?.transport,
  phase: manifest.stream_contract?.phase,
  snapshotSchema: snapshot.schema,
  snapshotLastSeq: snapshot.last_seq,
  eventsLen: events.length,
  firstSeq: events[0]?.seq,
  lastEventSeq: events.at(-1)?.seq,
}

record('1-manifest-schema', stream.manifestSchema === 'battle.transport_manifest.v1', JSON.stringify(stream))
record('2-file-backed-mode', stream.mode === 'file_backed_replay_stream', stream.mode)
record('3-mocked-false', stream.mocked === false, String(stream.mocked))
record('4-jsonl-transport', stream.transport === 'append_only_jsonl', stream.transport)
record('5-seq-contiguous', stream.eventsLen === 24 && stream.firstSeq === 1 && stream.lastEventSeq === 24 && stream.lastSeq === 24, JSON.stringify(stream))
record('6-snapshot-aligned', stream.snapshotSchema === 'battle.snapshot.v1' && stream.snapshotLastSeq === 24, JSON.stringify(stream))

await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:banner"]', { timeout: 20_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForTimeout(1500)

const chrome = await page.evaluate(() => {
  const text = document.body.textContent ?? ''
  return {
    banner: !!document.querySelector('[data-qid="battle:live:banner"]'),
    mode: document.querySelector('[data-qid="battle:live:banner:mode"]')?.textContent ?? '',
    phase: document.querySelector('[data-qid="battle:live:banner:phase"]')?.textContent ?? '',
    mocked: document.querySelector('[data-qid="battle:live:banner:mocked"]')?.textContent ?? '',
    status: document.querySelector('[data-qid="battle:live:status"]')?.textContent ?? '',
    seq: document.querySelector('[data-qid="battle:live:seq"]')?.textContent ?? '',
    transport: document.querySelector('[data-qid="battle:live:transport"]')?.textContent ?? '',
    following: !!document.querySelector('[data-qid="battle:live:following"]'),
    nav: !!document.querySelector('[data-qid="battle:nav:live"]'),
    pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    lane: !!document.querySelector('[data-qid="battle:lane:payload-857-receipt"]'),
    text,
  }
})

record('7-live-banner', chrome.banner, 'banner')
record('8-file-backed-badge', /FILE-BACKED STREAM/i.test(chrome.mode), chrome.mode)
record('9-phase-badge', /PHASE 2/i.test(chrome.phase), chrome.phase)
record('10-mocked-badge', /MOCKED:\s*NO/i.test(chrome.mocked), chrome.mocked)
record('11-seq-chrome', /seq\s+24\/24/i.test(chrome.seq), chrome.seq)
record('12-transport-chrome', /append_only_jsonl/i.test(chrome.transport), chrome.transport)
record('13-following-live', chrome.following, 'following')
record('14-pixi-engine', chrome.pixi === 'animated-sprites', chrome.pixi)
record('15-lane-present', chrome.lane, 'lane')
record('16-nav-live', chrome.nav, 'nav')
record(
  '17-no-raw-command-loop',
  !chrome.text.includes('command-loop/command-artifacts') && !chrome.text.includes('tau-dag-run/'),
  'paths',
)

// Scrub timeline early to leave live follow mode, then return
await page.waitForSelector('[data-qid="battle:timeline:scrub"]', { timeout: 20_000 })
const scrubbed = await page.evaluate(() => {
  const el = document.querySelector('[data-qid="battle:timeline:scrub"]')
  if (!el) return { ok: false, detail: 'missing scrub' }
  const rect = el.getBoundingClientRect()
  el.dispatchEvent(
    new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      clientX: rect.left + Math.max(12, rect.width * 0.08),
      clientY: rect.top + rect.height / 2,
      view: window,
    }),
  )
  return {
    ok: true,
    following: !!document.querySelector('[data-qid="battle:live:following"]'),
    returnBtn: !!document.querySelector('[data-qid="battle:live:return-to-live"]'),
    cursor: document.querySelector('[data-qid="battle:live:cursor"]')?.textContent ?? '',
    status: document.querySelector('[data-qid="battle:live:status"]')?.textContent ?? '',
  }
})
await page.waitForTimeout(400)
const scrubbedAfter = await page.evaluate(() => ({
  following: !!document.querySelector('[data-qid="battle:live:following"]'),
  returnBtn: !!document.querySelector('[data-qid="battle:live:return-to-live"]'),
  cursor: document.querySelector('[data-qid="battle:live:cursor"]')?.textContent ?? '',
  status: document.querySelector('[data-qid="battle:live:status"]')?.textContent ?? '',
}))
record('18-scrub-shows-return', scrubbedAfter.returnBtn && !scrubbedAfter.following, JSON.stringify({ scrubbed, scrubbedAfter }))
await page.click('[data-qid="battle:live:return-to-live"]')
await page.waitForTimeout(500)
const returned = await page.evaluate(() => ({
  following: !!document.querySelector('[data-qid="battle:live:following"]'),
  returnBtn: !!document.querySelector('[data-qid="battle:live:return-to-live"]'),
}))
record('19-return-to-live', returned.following && !returned.returnBtn, JSON.stringify(returned))
await page.screenshot({ path: resolve(outDir, '01-live-transport.png'), fullPage: true })

await page.goto(invalidUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:blocked"]', { timeout: 20_000 })
const invalid = await page.evaluate(() => ({
  banner: !!document.querySelector('[data-qid="battle:live:banner"]'),
  blocked: document.querySelector('[data-qid="battle:live:blocked"]')?.textContent ?? '',
}))
record(
  '20-unknown-fixture-fail-closed',
  !invalid.banner && /UNSUPPORTED FIXTURE/i.test(invalid.blocked),
  JSON.stringify(invalid),
)

record('21-no-page-errors', errors.length === 0, JSON.stringify(errors.slice(0, 5)))

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify({ host, url, mocked: false, live: true, checks, failed: failed.map((item) => item.id) }, null, 2),
)
await browser.close()
if (failed.length) {
  console.error(`prove-battle-pr8-live-transport failed: ${failed.map((item) => item.id).join(', ')}`)
  process.exit(1)
}
console.log(`prove-battle-pr8-live-transport passed ${checks.length}/${checks.length}`)
