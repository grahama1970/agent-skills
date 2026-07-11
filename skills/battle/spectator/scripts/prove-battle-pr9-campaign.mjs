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

const overture = await readFile(resolve(process.cwd(), 'public/battle-audio/score/v1/battle_intro_death_clock_overture.ogg'))
record('1-overture-ogg-present', overture.length > 10_000, String(overture.length))
const overtureHttp = await fetch(`${host}/battle-audio/score/v1/battle_intro_death_clock_overture.ogg`)
record('2-overture-http', overtureHttp.ok && (await overtureHttp.arrayBuffer()).byteLength === overture.length, String(overtureHttp.status))

const legacyMidi = await readFile(resolve(process.cwd(), 'public/battle-audio/legacy/battle-004-round-intro.mid'))
record('3-legacy-midi-present', legacyMidi.length > 100 && legacyMidi.slice(0, 4).toString() === 'MThd', String(legacyMidi.length))

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})

await page.goto(introUrl, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:intro"]', { timeout: 20_000 })
await page.waitForTimeout(800)
const intro = await page.evaluate(() => ({
  banner: !!document.querySelector('[data-qid="battle:intro"]'),
  page: document.querySelector('[data-qid="battle:intro"]')?.getAttribute('data-page') ?? '',
  style: document.querySelector('[data-qid="battle:intro:style"]')?.textContent ?? '',
  audioUrl: document.querySelector('[data-qid="battle:intro:audio-url"]')?.textContent ?? '',
  provisional: document.querySelector('[data-qid="battle:intro:provisional"]')?.textContent ?? '',
  legacySelectable: document.querySelector('[data-qid="battle:intro:legacy-selectable"]')?.textContent ?? '',
  legacyMidi: document.querySelector('[data-qid="battle:intro:legacy-midi"]')?.textContent ?? '',
  round: document.querySelector('[data-qid="battle:intro:round"]')?.textContent ?? '',
  text: document.body.textContent ?? '',
}))
record('4-death-clock-intro', intro.banner, 'intro')
record('5-graphic-style', /death_clock_round_intro/i.test(intro.style), intro.style)
record('6-audio-url', /battle_intro_death_clock_overture\.ogg/.test(intro.audioUrl), intro.audioUrl)
record('7-provisional-gm', /provisional_gm_render/i.test(intro.provisional), intro.provisional)
record('8-legacy-not-selectable', intro.legacySelectable === '0', intro.legacySelectable)
record('9-legacy-midi-path', /legacy\/battle-004-round-intro\.mid/.test(intro.legacyMidi), intro.legacyMidi)
record('10-round-label', /ROUND 1/i.test(intro.round), intro.round)
record('11-no-sega-license-claim', !/SEGA®|official sega soundtrack/i.test(intro.text), 'no sega license')

await page.click('[data-qid="battle:intro:audio"]')
await page.waitForTimeout(700)
const audioState = await page.evaluate(() => document.querySelector('[data-qid="battle:intro:audio-state"]')?.textContent ?? '')
record('12-overture-playing', /playing/i.test(audioState), audioState)

await page.click('[data-qid="battle:intro:start"]')
await page.waitForSelector('[data-qid="battle:campaign:banner"]', { timeout: 20_000 })
await page.waitForTimeout(600)
const afterStart = await page.evaluate(() => ({
  introGone: !document.querySelector('[data-qid="battle:intro"]'),
  campaign: !!document.querySelector('[data-qid="battle:campaign:banner"]'),
}))
record('13-start-enters-campaign', afterStart.introGone && afterStart.campaign, JSON.stringify(afterStart))
await page.screenshot({ path: resolve(outDir, '01-death-clock-intro-to-campaign.png'), fullPage: true })

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
record('14-chapter-count', /CHAPTERS\s+12/i.test(chrome.chapters), chrome.chapters)
const compositeBadge = await page.evaluate(() => document.querySelector('[data-qid="battle:campaign:composite"]')?.textContent ?? '')
record('14b-campaign-composite', /COMPOSITE DEMONSTRATION/i.test(compositeBadge), compositeBadge)
record('15-active-compile', /compile passes/i.test(chrome.activeTitle), chrome.activeTitle)
record('16-chapter-compile', chrome.chapterCompile, 'compile chapter')
record('17-no-false-victory', !chrome.chapterJudgeSuccess && chrome.notEmittedJudge, JSON.stringify({ chapterJudgeSuccess: chrome.chapterJudgeSuccess, notEmittedJudge: chrome.notEmittedJudge }))
record('18-nav-campaign', chrome.nav, 'nav')
record('19-pixi', chrome.pixi === 'animated-sprites', chrome.pixi)
record('20-no-raw-paths', !chrome.text.includes('tau-dag-run/') && !chrome.text.includes('command-loop/command-artifacts'), 'paths')
record('21-no-page-errors', errors.length === 0, JSON.stringify(errors.slice(0, 5)))

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify(
    {
      host,
      introUrl,
      arenaUrl,
      mocked: false,
      live: 'receipt_replay_campaign_death_clock_intro',
      provisional_gm_render: true,
      checks,
      failed: failed.map((item) => item.id),
      passCount: checks.filter((item) => item.pass).length,
      total: checks.length,
    },
    null,
    2,
  ),
)
await browser.close()
if (failed.length) {
  console.error(`prove:pr9-campaign FAILED ${failed.length}/${checks.length}`)
  process.exit(1)
}
console.log(`prove:pr9-campaign PASS ${checks.length}/${checks.length}`)
