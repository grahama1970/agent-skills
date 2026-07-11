#!/usr/bin/env node
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_CAMPAIGN_PROOF_DIR ?? '/tmp/battle-pr9-campaign-proof')
const introUrl = `${host}/#battle/campaign?engine=pixi&fixture=battle-004-pr6-genetic-pixi`
const arenaUrl = `${host}/#battle/campaign?engine=pixi&fixture=battle-004-pr6-genetic-pixi&pixiTest=1&pixiSeconds=114&particles=1&skipIntro=1`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

await mkdir(outDir, { recursive: true })

const midiBytes = await readFile(resolve(process.cwd(), 'public/battle-audio/battle-004-round-intro.mid'))
record('1-midi-file-present', midiBytes.length > 100 && midiBytes.slice(0, 4).toString() === 'MThd', String(midiBytes.length))
const midiHttp = await fetch(`${host}/battle-audio/battle-004-round-intro.mid`)
record('2-midi-http', midiHttp.ok && (await midiHttp.arrayBuffer()).byteLength === midiBytes.length, String(midiHttp.status))

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})

await page.goto(introUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:genesis:intro"]', { timeout: 20_000 })
await page.waitForTimeout(800)
const intro = await page.evaluate(() => ({
  banner: !!document.querySelector('[data-qid="battle:genesis:intro"]'),
  page: document.querySelector('[data-qid="battle:genesis:intro"]')?.getAttribute('data-page') ?? '',
  style: document.querySelector('[data-qid="battle:genesis:style"]')?.textContent ?? '',
  midiUrl: document.querySelector('[data-qid="battle:genesis:midi-url"]')?.textContent ?? '',
  round: document.querySelector('[data-qid="battle:genesis:round"]')?.textContent ?? '',
  lines: document.querySelector('[data-qid="battle:genesis:lines"]')?.textContent ?? '',
  text: document.body.textContent ?? '',
}))
record('3-genesis-intro', intro.banner, 'intro')
record('4-graphic-style', /sega_genesis_round_intro/i.test(intro.style), intro.style)
record('5-midi-url', /battle-004-round-intro\.mid/.test(intro.midiUrl), intro.midiUrl)
record('6-round-label', /ROUND 1/i.test(intro.round), intro.round)
record('7-no-sega-license-claim', !/SEGA®|official sega soundtrack/i.test(intro.text), 'no sega license')

await page.click('[data-qid="battle:genesis:midi"]')
await page.waitForTimeout(500)
const midiState = await page.evaluate(() => document.querySelector('[data-qid="battle:genesis:midi-state"]')?.textContent ?? '')
record('8-midi-playing', /playing/i.test(midiState), midiState)

await page.click('[data-qid="battle:genesis:start"]')
await page.waitForSelector('[data-qid="battle:campaign:banner"]', { timeout: 20_000 })
await page.waitForTimeout(600)
const afterStart = await page.evaluate(() => ({
  introGone: !document.querySelector('[data-qid="battle:genesis:intro"]'),
  campaign: !!document.querySelector('[data-qid="battle:campaign:banner"]'),
}))
record('9-start-enters-campaign', afterStart.introGone && afterStart.campaign, JSON.stringify(afterStart))
await page.screenshot({ path: resolve(outDir, '01-genesis-intro-to-campaign.png'), fullPage: true })

await page.goto(arenaUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:campaign:banner"]', { timeout: 20_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForTimeout(1000)
const chrome = await page.evaluate(() => {
  const text = document.body.textContent ?? ''
  return {
    chapters: document.querySelector('[data-qid="battle:campaign:banner:chapters"]')?.textContent ?? '',
    activeTitle: document.querySelector('[data-qid="battle:campaign:active-title"]')?.textContent ?? '',
    chapterCompile: !!document.querySelector('[data-qid="battle:campaign:chapter:compile_passed"]'),
    chapterJudgeSuccess: !!document.querySelector('[data-qid="battle:campaign:chapter:judge_exploit_success"]'),
    notEmittedJudge: !!document.querySelector('[data-qid="battle:genetic:not-emitted:judge_exploit_success"]'),
    nav: !!document.querySelector('[data-qid="battle:nav:campaign"]'),
    pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    text,
  }
})
record('10-chapter-count', /CHAPTERS\s+12/i.test(chrome.chapters), chrome.chapters)
record('11-active-compile', /compile passes/i.test(chrome.activeTitle), chrome.activeTitle)
record('12-chapter-compile', chrome.chapterCompile, 'compile chapter')
record('13-no-false-victory', !chrome.chapterJudgeSuccess && chrome.notEmittedJudge, JSON.stringify({ chapterJudgeSuccess: chrome.chapterJudgeSuccess, notEmittedJudge: chrome.notEmittedJudge }))
record('14-nav-campaign', chrome.nav, 'nav')
record('15-pixi', chrome.pixi === 'animated-sprites', chrome.pixi)
record('16-no-raw-paths', !chrome.text.includes('tau-dag-run/') && !chrome.text.includes('command-loop/command-artifacts'), 'paths')
record('17-no-page-errors', errors.length === 0, JSON.stringify(errors.slice(0, 5)))

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify(
    {
      host,
      introUrl,
      arenaUrl,
      mocked: false,
      live: 'receipt_replay_campaign_genesis_intro',
      research: [
        'Streets of Rage Genesis intro flow',
        'VGMusic/Project2612 listening refs',
        'CC0 free_vgms / OpenGameArt chiptune alternatives',
      ],
      checks,
      failed: failed.map((item) => item.id),
    },
    null,
    2,
  ),
)
await browser.close()
if (failed.length) {
  console.error(`prove-battle-pr9-campaign failed: ${failed.map((item) => item.id).join(', ')}`)
  process.exit(1)
}
console.log(`prove-battle-pr9-campaign passed ${checks.length}/${checks.length}`)
