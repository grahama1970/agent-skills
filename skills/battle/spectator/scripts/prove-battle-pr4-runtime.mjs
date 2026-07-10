#!/usr/bin/env node
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const url = `${host}/#battle/runtime?fixture=battle-004-pr4`
const invalidUrl = `${host}/#battle/runtime?fixture=not-a-registered-fixture`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1700 } })

await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:runtime:root"]', { timeout: 20000 })

const proof = await page.evaluate(() => {
  const root = document.querySelector('[data-qid="battle:runtime:root"]')
  const text = root?.textContent ?? ''
  const banners = [...document.querySelectorAll('[data-qid^="battle:runtime:banner:"]')].map((el) => el.textContent?.trim())
  const image = document.querySelector('[data-qid="battle:runtime:docker:image"]')?.textContent ?? ''
  const network = document.querySelector('[data-qid="battle:runtime:docker:network"]')?.textContent ?? ''
  const timeout = document.querySelector('[data-qid="battle:runtime:docker:timeout"]')?.textContent ?? ''
  const judgeStatus = document.querySelector('[data-qid="battle:runtime:judge:status"]')?.textContent ?? ''
  const judgeVerified = document.querySelector('[data-qid="battle:runtime:judge:verified"]')?.textContent ?? ''
  const progression = document.querySelector('[data-qid="battle:runtime:judge:progression"]')?.textContent ?? ''
  const mustNot = document.querySelector('[data-qid="battle:runtime:claim-must-not"]')?.textContent ?? ''
  const may = document.querySelector('[data-qid="battle:runtime:claim-may"]')?.textContent ?? ''
  const targetFlag = document.querySelector('[data-qid="battle:runtime:claim:target-not-exploit"]')?.textContent ?? ''
  const targetUnproven = document.querySelector('[data-qid="battle:runtime:summary:target-unproven"]')?.textContent ?? ''
  const run1 = document.querySelector('[data-qid="battle:runtime:run:specimen-0001"]')?.textContent ?? ''
  const run4 = document.querySelector('[data-qid="battle:runtime:run:specimen-0004"]')?.textContent ?? ''
  const run4Target = document.querySelector('[data-qid="battle:runtime:run:specimen-0004:target"]')?.textContent ?? ''
  const runButtons = [...document.querySelectorAll('button, a')].filter((el) =>
    /^(run|execute|retry|invoke tau|approve spawn)$/i.test((el.textContent ?? '').trim()),
  )
  return {
    root: !!root,
    text,
    banners,
    image,
    network,
    timeout,
    judgeStatus,
    judgeVerified,
    progression,
    mustNot,
    may,
    targetFlag,
    targetUnproven,
    run1,
    run4,
    run4Target,
    runButtons: runButtons.map((el) => el.textContent?.trim()),
    headline: document.querySelector('[data-qid="battle:runtime:headline"]')?.textContent?.trim() ?? '',
    pixi: !!document.querySelector('[data-battle-pixi-engine]'),
    nav: !!document.querySelector('[data-qid="battle:nav:runtime"]'),
  }
})

record('1-runtime-root', proof.root, url)
record('2-docker-banner', proof.banners.some((b) => /DOCKER RUNTIME RECORDED/i.test(b ?? '')), JSON.stringify(proof.banners))
record('3-judge-not-run-banner', proof.banners.some((b) => /JUDGE NOT RUN/i.test(b ?? '')), JSON.stringify(proof.banners))
record('4-exploit-not-proven-banner', proof.banners.some((b) => /EXPLOIT SUCCESS NOT PROVEN/i.test(b ?? '')), JSON.stringify(proof.banners))
record('5-target-unproven-banner', proof.banners.some((b) => /TARGET CONTACT UNPROVEN/i.test(b ?? '')), JSON.stringify(proof.banners))
record('6-docker-image', /python:3\.12-slim/i.test(proof.image), proof.image)
record('7-docker-network-none', /network\s*none/i.test(proof.network), proof.network)
record('8-docker-timeout', /30/i.test(proof.timeout), proof.timeout)
record('9-judge-not-run', /NOT_RUN/i.test(proof.judgeStatus), proof.judgeStatus)
record('10-judge-verified-zero', /0/.test(proof.judgeVerified), proof.judgeVerified)
record('11-judge-progression', /JUDGE_NOT_RUN/i.test(proof.progression), proof.progression)
record('12-compile-failed-run', /COMPILE_FAILED/i.test(proof.run1), proof.run1.slice(0, 160))
record('13-target-contact-unproven-run', /TARGET_CONTACT_UNPROVEN/i.test(proof.run4) && /TARGET_CONTACT_UNPROVEN/i.test(proof.run4Target), JSON.stringify({ run4: proof.run4.slice(0,160), target: proof.run4Target }))
record('14-target-unproven-count', /2/.test(proof.targetUnproven), proof.targetUnproven)
record('15-must-not-exploit-success', /exploit success/i.test(proof.mustNot) && !/exploit success/i.test(proof.may), JSON.stringify({ mustNot: proof.mustNot.slice(0,220), may: proof.may.slice(0,220) }))
record('16-target-not-exploit-flag', /target_contact_is_not_exploit_success:\s*true/i.test(proof.targetFlag), proof.targetFlag)
record('17-no-tau-paths', !proof.text.includes('command-loop/command-artifacts') && !proof.text.includes('tau-dag-run/'), 'checked')
record('18-no-run-execute-button', proof.runButtons.length === 0, JSON.stringify(proof.runButtons))
record('19-no-pixi', !proof.pixi, 'pixi absent')
record('20-nav-runtime', proof.nav, 'nav')

await page.goto(invalidUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(() => Boolean(document.querySelector('[data-qid="battle:runtime:error"]')), null, { timeout: 15000 })
const invalid = await page.evaluate(() => ({
  title: document.querySelector('[data-qid="battle:runtime:error"]')?.textContent ?? '',
}))
record('21-invalid-fixture-fails-closed', /UNSUPPORTED FIXTURE/i.test(invalid.title), invalid.title)

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_PR4_RUNTIME_PASS')
