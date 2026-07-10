#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_GENETIC_PIXI_PROOF_DIR ?? '/tmp/battle-pr6-genetic-pixi-proof')
const url = `${host}/#battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

function urlAt(seconds) {
  return `${url}&pixiTest=1&pixiSeconds=${seconds}`
}

await mkdir(outDir, { recursive: true })
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})

const fixture = await (await fetch(`${host}/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json`)).json()
record(
  '1-fixture-fetch',
  fixture?.genetic_lifecycle?.schema === 'battle.genetic_lifecycle_events.v1' && fixture?.mocked === false,
  JSON.stringify({ schema: fixture?.genetic_lifecycle?.schema, mocked: fixture?.mocked }),
)

await page.goto(urlAt(86.2), { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:genetic:banner"]', { timeout: 20_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForTimeout(1200)

const chrome = await page.evaluate(() => {
  const root = document.body.textContent ?? ''
  return {
    banner: !!document.querySelector('[data-qid="battle:genetic:banner"]'),
    noVictory: !!document.querySelector('[data-qid="battle:genetic:banner:no-victory"]'),
    compileNotRunnable: !!document.querySelector('[data-qid="battle:genetic:banner:compile-not-runnable"]'),
    targetNotExploit: !!document.querySelector('[data-qid="battle:genetic:banner:target-not-exploit"]'),
    presentCount: document.querySelector('[data-qid="battle:genetic:present-count"]')?.textContent ?? '',
    notEmitted: [...document.querySelectorAll('[data-qid^="battle:genetic:not-emitted:"]')].map((el) => el.getAttribute('data-qid')),
    present: [...document.querySelectorAll('[data-qid^="battle:genetic:present:"]')].map((el) => el.getAttribute('data-qid')),
    mustNot: document.querySelector('[data-qid="battle:genetic:claim-must-not"]')?.textContent ?? '',
    may: document.querySelector('[data-qid="battle:genetic:claim-may"]')?.textContent ?? '',
    nav: !!document.querySelector('[data-qid="battle:nav:genetic"]'),
    pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    text: root,
  }
})

record('2-genetic-banner', chrome.banner, 'banner')
record('3-no-victory-banner', chrome.noVictory, 'no victory')
record('4-compile-not-runnable-banner', chrome.compileNotRunnable, 'compile')
record('5-target-not-exploit-banner', chrome.targetNotExploit, 'target')
record('6-present-count', /present\s+12/i.test(chrome.presentCount), chrome.presentCount)
record(
  '7-not-emitted-types',
  ['repair_started', 'repair_materialized', 'judge_exploit_success', 'genome_promoted'].every((item) =>
    chrome.notEmitted.some((qid) => qid?.includes(item)),
  ),
  JSON.stringify(chrome.notEmitted),
)
record('8-present-research', chrome.present.some((qid) => qid?.includes('research_started')), JSON.stringify(chrome.present.slice(0, 5)))
record('9-must-not-exploit', /exploit success|judge success/i.test(chrome.mustNot), chrome.mustNot.slice(0, 180))
record('10-nav-genetic', chrome.nav, 'nav')
record('11-pixi-engine', chrome.pixi === 'animated-sprites', chrome.pixi)
record(
  '12-no-raw-paths',
  !chrome.text.includes('tau-dag-run/') && !chrome.text.includes('command-loop/command-artifacts'),
  'paths',
)

const research = await page.evaluate(() => {
  const stage = document.querySelector('[data-qid="battle:pixi:stage"]')
  return {
    beatKind: stage?.dataset.battleReceiptBeatKind ?? null,
    emphasis: stage?.dataset.battleReceiptBeatEmphasis ?? null,
    vfx: stage?.dataset.battleReceiptBeatVfx ?? null,
  }
})
record(
  '13-research-scan-vfx',
  research.beatKind === 'research_started' && research.emphasis === 'research_scan' && research.vfx === 'genetic',
  JSON.stringify(research),
)
await page.screenshot({ path: resolve(outDir, '01-research-scan.png'), fullPage: true })

await page.goto(urlAt(108.2), { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForTimeout(1200)
const compileFailed = await page.evaluate(() => {
  const stage = document.querySelector('[data-qid="battle:pixi:stage"]')
  return {
    beatKind: stage?.dataset.battleReceiptBeatKind ?? null,
    emphasis: stage?.dataset.battleReceiptBeatEmphasis ?? null,
    vfx: stage?.dataset.battleReceiptBeatVfx ?? null,
  }
})
record(
  '14-compile-error-vfx',
  compileFailed.beatKind === 'compile_failed' && compileFailed.emphasis === 'compile_error' && compileFailed.vfx === 'genetic',
  JSON.stringify(compileFailed),
)
await page.screenshot({ path: resolve(outDir, '02-compile-error.png'), fullPage: true })

await page.goto(urlAt(114.2), { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForTimeout(1200)
const compilePassed = await page.evaluate(() => {
  const stage = document.querySelector('[data-qid="battle:pixi:stage"]')
  const text = document.body.textContent ?? ''
  return {
    beatKind: stage?.dataset.battleReceiptBeatKind ?? null,
    emphasis: stage?.dataset.battleReceiptBeatEmphasis ?? null,
    vfx: stage?.dataset.battleReceiptBeatVfx ?? null,
    claimsVictory: /VICTORY|EXPLOIT SUCCESS CONFIRMED/i.test(text) && !/NOT_EMITTED:judge_exploit_success/i.test(text),
  }
})
record(
  '15-compile-lock-no-victory',
  compilePassed.beatKind === 'compile_passed' &&
    compilePassed.emphasis === 'compile_lock' &&
    compilePassed.vfx === 'genetic' &&
    compilePassed.claimsVictory === false,
  JSON.stringify(compilePassed),
)
await page.screenshot({ path: resolve(outDir, '03-compile-lock.png'), fullPage: true })

await page.goto(urlAt(116.2), { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForTimeout(1200)
const target = await page.evaluate(() => {
  const stage = document.querySelector('[data-qid="battle:pixi:stage"]')
  return {
    beatKind: stage?.dataset.battleReceiptBeatKind ?? null,
    emphasis: stage?.dataset.battleReceiptBeatEmphasis ?? null,
    vfx: stage?.dataset.battleReceiptBeatVfx ?? null,
  }
})
record(
  '16-endpoint-pulse-no-victory',
  target.beatKind === 'target_contact_unproven' && target.emphasis === 'endpoint_pulse' && target.vfx === 'genetic',
  JSON.stringify(target),
)
await page.screenshot({ path: resolve(outDir, '04-endpoint-pulse.png'), fullPage: true })

record('17-no-page-errors', errors.length === 0, JSON.stringify(errors.slice(0, 5)))

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify({ host, url, mocked: false, live: true, checks, failed: failed.map((item) => item.id) }, null, 2),
)
await browser.close()
if (failed.length) {
  console.error(`prove-battle-pr6-genetic-pixi failed: ${failed.map((item) => item.id).join(', ')}`)
  process.exit(1)
}
console.log(`prove-battle-pr6-genetic-pixi passed ${checks.length}/${checks.length}`)
