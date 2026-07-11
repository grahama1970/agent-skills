#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_LIVE_TRANSPORT_PROOF_DIR ?? '/tmp/battle-pr8-live-transport-proof')
const contractUrl = `${host}/#battle/live?engine=pixi&battle=battle-004`
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
record('2-contract-only', contractJson.live === 'contract_only' && contractJson.mocked === false, JSON.stringify({ live: contractJson.live, mocked: contractJson.mocked }))
record('3-sse-shape', contractJson.transport?.kind === 'sse' && contractJson.transport?.content_type === 'text/event-stream', JSON.stringify(contractJson.transport))
record('4-genetic-16', contractJson.event_stream?.genetic_event_types_when_live?.length === 16, String(contractJson.event_stream?.genetic_event_types_when_live?.length))
record(
  '5-must-not-endpoint',
  Array.isArray(contractJson.claim_boundary?.must_not_claim) &&
    contractJson.claim_boundary.must_not_claim.includes('sse_endpoint_implemented') &&
    contractJson.claim_boundary.live_contract_is_not_endpoint_execution === true,
  JSON.stringify(contractJson.claim_boundary?.must_not_claim?.slice(0, 4)),
)

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})

await page.goto(contractUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:banner"]', { timeout: 20_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForTimeout(1200)

const chrome = await page.evaluate(() => {
  const text = document.body.textContent ?? ''
  return {
    banner: !!document.querySelector('[data-qid="battle:live:banner"]'),
    mode: document.querySelector('[data-qid="battle:live:banner:mode"]')?.textContent ?? '',
    contractOnly: document.querySelector('[data-qid="battle:live:banner:contract-only"]')?.textContent ?? '',
    noEndpoint: document.querySelector('[data-qid="battle:live:banner:no-endpoint"]')?.textContent ?? '',
    mocked: document.querySelector('[data-qid="battle:live:banner:mocked"]')?.textContent ?? '',
    sseClient: document.querySelector('[data-qid="battle:live:sse-client"]')?.textContent ?? '',
    geneticCount: document.querySelector('[data-qid="battle:live:genetic-count"]')?.textContent ?? '',
    sseEndpoint: document.querySelector('[data-qid="battle:live:sse-endpoint"]')?.textContent ?? '',
    mustNot: document.querySelector('[data-qid="battle:live:claim-must-not"]')?.textContent ?? '',
    may: document.querySelector('[data-qid="battle:live:claim-may"]')?.textContent ?? '',
    geneticTypes: [...document.querySelectorAll('[data-qid^="battle:live:genetic:"]')].map((el) => el.getAttribute('data-qid')),
    nav: !!document.querySelector('[data-qid="battle:nav:live"]'),
    pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    geneticBanner: !!document.querySelector('[data-qid="battle:genetic:banner"]'),
    text,
  }
})

record('6-contract-banner', chrome.banner, 'banner')
record('7-sse-contract-badge', /SSE CONTRACT/i.test(chrome.mode), chrome.mode)
record('8-contract-only-badge', /CONTRACT ONLY/i.test(chrome.contractOnly), chrome.contractOnly)
record('9-no-endpoint-badge', /NOT EXECUTED/i.test(chrome.noEndpoint), chrome.noEndpoint)
record('10-mocked-no', /MOCKED:\s*NO/i.test(chrome.mocked), chrome.mocked)
record('11-sse-client-blocked', /contract_only_blocked/i.test(chrome.sseClient), chrome.sseClient)
record('12-genetic-count', /genetic types\s+16/i.test(chrome.geneticCount), chrome.geneticCount)
record('13-sse-endpoint-shape', /\/battle\/live\/battle-004\/events/.test(chrome.sseEndpoint), chrome.sseEndpoint)
record('14-must-not-sse-implemented', /sse endpoint implemented/i.test(chrome.mustNot), chrome.mustNot.slice(0, 200))
record('15-may-contract-published', /backend live transport contract published/i.test(chrome.may), chrome.may.slice(0, 200))
record('16-genetic-types-rendered', chrome.geneticTypes.includes('battle:live:genetic:research_started') && chrome.geneticTypes.includes('battle:live:genetic:judge_exploit_success'), JSON.stringify(chrome.geneticTypes.slice(0, 5)))
record('17-pixi-backdrop', chrome.pixi === 'animated-sprites', chrome.pixi)
record('18-genetic-companion-banner', chrome.geneticBanner, 'genetic banner')
record('19-nav-live', chrome.nav, 'nav')
record(
  '20-no-raw-paths',
  !chrome.text.includes('tau-dag-run/') && !chrome.text.includes('command-loop/command-artifacts'),
  'paths',
)
record('21-no-false-live-claim', !/SSE CONNECTED|LIVE STREAM EXECUTING/i.test(chrome.text), 'no false live')

await page.screenshot({ path: resolve(outDir, '01-live-transport-contract.png'), fullPage: true })

await page.goto(fileBackedUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:banner"]', { timeout: 20_000 })
const fileBacked = await page.evaluate(() => ({
  mode: document.querySelector('[data-qid="battle:live:banner:mode"]')?.textContent ?? '',
  seq: document.querySelector('[data-qid="battle:live:seq"]')?.textContent ?? '',
}))
record('22-file-backed-still-works', /FILE-BACKED STREAM/i.test(fileBacked.mode) && /24\/24/.test(fileBacked.seq), JSON.stringify(fileBacked))

await page.goto(invalidUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:live:blocked"]', { timeout: 20_000 })
const invalid = await page.evaluate(() => document.querySelector('[data-qid="battle:live:blocked"]')?.textContent ?? '')
record('23-unknown-battle-fail-closed', /UNSUPPORTED/i.test(invalid), invalid)

record('24-no-page-errors', errors.length === 0, JSON.stringify(errors.slice(0, 5)))

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify({ host, contractUrl, mocked: false, live: 'contract_only', checks, failed: failed.map((item) => item.id) }, null, 2),
)
await browser.close()
if (failed.length) {
  console.error(`prove-battle-pr8-live-transport failed: ${failed.map((item) => item.id).join(', ')}`)
  process.exit(1)
}
console.log(`prove-battle-pr8-live-transport passed ${checks.length}/${checks.length}`)
