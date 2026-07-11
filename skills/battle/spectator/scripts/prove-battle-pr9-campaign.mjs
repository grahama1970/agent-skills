#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_CAMPAIGN_PROOF_DIR ?? '/tmp/battle-pr9-campaign-proof')
const url = `${host}/#battle/campaign?engine=pixi&fixture=battle-004-pr6-genetic-pixi&pixiTest=1&pixiSeconds=114&particles=1`
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

const fixture = await (await fetch(`${host}/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json`)).json()
record('1-fixture-genetic', fixture?.genetic_lifecycle?.schema === 'battle.genetic_lifecycle_events.v1' && fixture?.mocked === false, JSON.stringify({ schema: fixture?.genetic_lifecycle?.schema, mocked: fixture?.mocked }))

await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:campaign:banner"]', { timeout: 20_000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
await page.waitForTimeout(1200)

const chrome = await page.evaluate(() => {
  const text = document.body.textContent ?? ''
  return {
    banner: !!document.querySelector('[data-qid="battle:campaign:banner"]'),
    mode: document.querySelector('[data-qid="battle:campaign:banner:mode"]')?.textContent ?? '',
    mocked: document.querySelector('[data-qid="battle:campaign:banner:mocked"]')?.textContent ?? '',
    chapters: document.querySelector('[data-qid="battle:campaign:banner:chapters"]')?.textContent ?? '',
    noVictory: document.querySelector('[data-qid="battle:campaign:banner:no-victory"]')?.textContent ?? '',
    activeTitle: document.querySelector('[data-qid="battle:campaign:active-title"]')?.textContent ?? '',
    activeCaption: document.querySelector('[data-qid="battle:campaign:active-caption"]')?.textContent ?? '',
    pulseLineages: document.querySelector('[data-qid="battle:campaign:pulse:lineages"]')?.textContent ?? '',
    particles: document.querySelector('[data-qid="battle:campaign:particles"]')?.textContent ?? '',
    reducedMotion: document.querySelector('[data-qid="battle:campaign:reduced-motion"]')?.textContent ?? '',
    soundArm: !!document.querySelector('[data-qid="battle:campaign:sound-arm"]'),
    chapterResearch: !!document.querySelector('[data-qid="battle:campaign:chapter:research_started"]'),
    chapterCompile: !!document.querySelector('[data-qid="battle:campaign:chapter:compile_passed"]'),
    chapterBranch: !!document.querySelector('[data-qid="battle:campaign:chapter:branch_abandoned"]'),
    chapterJudgeSuccess: !!document.querySelector('[data-qid="battle:campaign:chapter:judge_exploit_success"]'),
    notEmittedJudge: !!document.querySelector('[data-qid="battle:genetic:not-emitted:judge_exploit_success"]'),
    may: document.querySelector('[data-qid="battle:campaign:claim-may"]')?.textContent ?? '',
    mustNot: document.querySelector('[data-qid="battle:campaign:claim-must-not"]')?.textContent ?? '',
    nav: !!document.querySelector('[data-qid="battle:nav:campaign"]'),
    geneticBanner: !!document.querySelector('[data-qid="battle:genetic:banner"]'),
    pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    text,
  }
})

record('2-campaign-banner', chrome.banner, 'banner')
record('3-mode-badge', /CAMPAIGN STORY/i.test(chrome.mode), chrome.mode)
record('4-mocked-no', /MOCKED:\s*NO/i.test(chrome.mocked), chrome.mocked)
record('5-chapter-count', /CHAPTERS\s+12/i.test(chrome.chapters), chrome.chapters)
record('6-no-victory-badge', /NO VICTORY/i.test(chrome.noVictory), chrome.noVictory)
record('7-active-compile', /compile passes/i.test(chrome.activeTitle), chrome.activeTitle)
record('8-active-caption', /not runtime|compile/i.test(chrome.activeCaption), chrome.activeCaption.slice(0, 120))
record('9-pulse-lineages', /lineages\s+\d+/i.test(chrome.pulseLineages), chrome.pulseLineages)
record('10-particles-on', /particles on/i.test(chrome.particles), chrome.particles)
record('11-reduced-motion-off', /reduced motion off/i.test(chrome.reducedMotion), chrome.reducedMotion)
record('12-sound-arm', chrome.soundArm, 'sound arm')
record('13-chapter-research', chrome.chapterResearch, 'research chapter')
record('14-chapter-compile', chrome.chapterCompile, 'compile chapter')
record('15-chapter-branch', chrome.chapterBranch, 'branch chapter')
record('16-may-story', /campaign story chapters/i.test(chrome.may), chrome.may.slice(0, 160))
record('17-must-not-exploit', /exploit success|sound is not proof|compile passed is not runnable/i.test(chrome.mustNot), chrome.mustNot.slice(0, 200))
record('18-nav-campaign', chrome.nav, 'nav')
record('19-genetic-banner', chrome.geneticBanner, 'genetic')
record('20-pixi', chrome.pixi === 'animated-sprites', chrome.pixi)
record(
  '21-no-raw-paths',
  !chrome.text.includes('tau-dag-run/') && !chrome.text.includes('command-loop/command-artifacts'),
  'paths',
)
record('22-no-false-victory', !chrome.chapterJudgeSuccess && chrome.notEmittedJudge, JSON.stringify({ chapterJudgeSuccess: chrome.chapterJudgeSuccess, notEmittedJudge: chrome.notEmittedJudge }))

await page.screenshot({ path: resolve(outDir, '01-campaign-story.png'), fullPage: true })

await page.click('[data-qid="battle:campaign:sound-arm"]')
await page.waitForTimeout(200)
const armed = await page.evaluate(() => document.querySelector('[data-qid="battle:campaign:sound-caption"]')?.textContent ?? '')
record('23-sound-caption', /Sound caption/i.test(armed), armed)

await page.click('[data-qid="battle:campaign:chapter:research_started"]')
await page.waitForTimeout(400)
const jumped = await page.evaluate(() => ({
  title: document.querySelector('[data-qid="battle:campaign:active-title"]')?.textContent ?? '',
  caption: document.querySelector('[data-qid="battle:campaign:sound-caption"]')?.textContent ?? '',
}))
record('24-chapter-jump', /Research opens/i.test(jumped.title), JSON.stringify(jumped))

record('25-no-page-errors', errors.length === 0, JSON.stringify(errors.slice(0, 5)))

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify({ host, url, mocked: false, live: 'receipt_replay_campaign', checks, failed: failed.map((item) => item.id) }, null, 2),
)
await browser.close()
if (failed.length) {
  console.error(`prove-battle-pr9-campaign failed: ${failed.map((item) => item.id).join(', ')}`)
  process.exit(1)
}
console.log(`prove-battle-pr9-campaign passed ${checks.length}/${checks.length}`)
