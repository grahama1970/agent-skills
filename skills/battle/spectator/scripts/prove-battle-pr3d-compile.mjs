#!/usr/bin/env node
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const url = `${host}/#battle/compile?fixture=battle-004-pr3d`
const invalidUrl = `${host}/#battle/compile?fixture=not-a-registered-fixture`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1600 } })

await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:compile:root"]', { timeout: 20000 })

const proof = await page.evaluate(() => {
  const root = document.querySelector('[data-qid="battle:compile:root"]')
  const text = root?.textContent ?? ''
  const banners = [...document.querySelectorAll('[data-qid^="battle:compile:banner:"]')].map((el) => el.textContent?.trim())
  const compileNode = document.querySelector('[data-qid="battle:compile:node:compile-repair"]')?.textContent ?? ''
  const authorNode = document.querySelector('[data-qid="battle:compile:node:exploit-code-author"]')?.textContent ?? ''
  const stderr = document.querySelector('[data-qid="battle:compile:stderr:preview"]')?.textContent ?? ''
  const mustNot = document.querySelector('[data-qid="battle:compile:claim-must-not"]')?.textContent ?? ''
  const may = document.querySelector('[data-qid="battle:compile:claim-may"]')?.textContent ?? ''
  const notRunnable = document.querySelector('[data-qid="battle:compile:claim:not-runnable"]')?.textContent ?? ''
  const repairAttempted = document.querySelector('[data-qid="battle:compile:repair:attempted"]')?.textContent ?? ''
  const selected = document.querySelector('[data-qid="battle:compile:selected:id"]')?.textContent ?? ''
  const v001 = document.querySelector('[data-qid="battle:compile:version:v001"]')?.textContent ?? ''
  const v002 = document.querySelector('[data-qid="battle:compile:version:v002"]')?.textContent ?? ''
  const runtime = document.querySelector('[data-qid="battle:compile:boundary:runtime_status"]')?.textContent ?? ''
  const flags = document.querySelector('[data-qid="battle:compile:attempt:flags"]')?.textContent ?? ''
  const runButtons = [...document.querySelectorAll('button, a')].filter((el) =>
    /^(run|execute|retry|invoke tau|approve spawn)$/i.test((el.textContent ?? '').trim()),
  )
  return {
    root: !!root,
    text,
    banners,
    compileNode,
    authorNode,
    stderr,
    mustNot,
    may,
    notRunnable,
    repairAttempted,
    selected,
    v001,
    v002,
    runtime,
    flags,
    runButtons: runButtons.map((el) => el.textContent?.trim()),
    headline: document.querySelector('[data-qid="battle:compile:headline"]')?.textContent?.trim() ?? '',
    pixi: !!document.querySelector('[data-battle-pixi-engine]'),
    nav: !!document.querySelector('[data-qid="battle:nav:compile"]'),
  }
})

record('1-compile-root', proof.root, url)
record('2-compile-failed-banner', proof.banners.some((b) => /COMPILE FAILED/i.test(b ?? '')), JSON.stringify(proof.banners))
record('3-not-runnable-banner', proof.banners.some((b) => /NOT RUNNABLE/i.test(b ?? '')), JSON.stringify(proof.banners))
record('4-runtime-not-run-banner', proof.banners.some((b) => /RUNTIME NOT RUN/i.test(b ?? '')), JSON.stringify(proof.banners))
record('5-compile-repair-blocked', /BLOCKED/i.test(proof.compileNode), proof.compileNode)
record('6-code-author-pass', /PASS/i.test(proof.authorNode), proof.authorNode)
record('7-stderr-syntax-error', /SyntaxError/i.test(proof.stderr), proof.stderr.slice(0, 240))
record('8-versions-present', /v001/i.test(proof.v001) && /v002/i.test(proof.v002) && /FAILED/i.test(proof.v002), JSON.stringify({ v001: proof.v001.slice(0,120), v002: proof.v002.slice(0,120) }))
record('9-selected-v002', /v002/i.test(proof.selected), proof.selected)
record('10-repair-not-attempted', /repair attempted\s*no/i.test(proof.repairAttempted), proof.repairAttempted)
record('11-runtime-not-run', /NOT_RUN/i.test(proof.runtime), proof.runtime)
record('12-compile-failed-flags', /failed\s*yes/i.test(proof.flags) && /passed\s*no/i.test(proof.flags), proof.flags)
record('13-must-not-runnable', /runnable/i.test(proof.mustNot) && !/runnable/i.test(proof.may), JSON.stringify({ mustNot: proof.mustNot.slice(0,200), may: proof.may.slice(0,200) }))
record('14-compile-passed-not-runnable-flag', /compile_passed_is_not_runnable:\s*true/i.test(proof.notRunnable), proof.notRunnable)
record('15-no-tau-paths', !proof.text.includes('command-loop/command-artifacts') && !proof.text.includes('tau-dag-run/'), 'checked')
record('16-no-run-execute-button', proof.runButtons.length === 0, JSON.stringify(proof.runButtons))
record('17-no-pixi', !proof.pixi, 'pixi absent')
record('18-nav-compile', proof.nav, 'nav')

await page.goto(invalidUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(() => Boolean(document.querySelector('[data-qid="battle:compile:error"]')), null, { timeout: 15000 })
const invalid = await page.evaluate(() => ({
  title: document.querySelector('[data-qid="battle:compile:error"]')?.textContent ?? '',
}))
record('19-invalid-fixture-fails-closed', /UNSUPPORTED FIXTURE/i.test(invalid.title), invalid.title)

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_PR3D_COMPILE_PASS')
