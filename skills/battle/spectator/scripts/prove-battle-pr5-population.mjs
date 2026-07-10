#!/usr/bin/env node
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const url = `${host}/#battle/population?fixture=battle-004-pr5-population`
const invalidUrl = `${host}/#battle/population?fixture=not-a-registered-fixture`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1800 } })

await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:population:root"]', { timeout: 20000 })

const proof = await page.evaluate(() => {
  const root = document.querySelector('[data-qid="battle:population:root"]')
  const text = root?.textContent ?? ''
  const banners = [...document.querySelectorAll('[data-qid^="battle:population:banner:"]')].map((el) => el.textContent?.trim())
  const specimens = ['specimen-0001', 'specimen-0002', 'specimen-0003', 'specimen-0004'].map(
    (id) => document.querySelector(`[data-qid="battle:population:specimen:${id}"]`)?.textContent ?? '',
  )
  const gens = [0, 1, 2, 3].map((g) => document.querySelector(`[data-qid="battle:population:generation:${g}"]`)?.textContent ?? '')
  const edges = document.querySelector('[data-qid="battle:population:lineage:summary"]')?.textContent ?? ''
  const mustNot = document.querySelector('[data-qid="battle:population:claim-must-not"]')?.textContent ?? ''
  const may = document.querySelector('[data-qid="battle:population:claim-may"]')?.textContent ?? ''
  const engine = document.querySelector('[data-qid="battle:population:campaign:engine"]')?.textContent ?? ''
  const notEngine = document.querySelector('[data-qid="battle:population:claim:not-engine"]')?.textContent ?? ''
  const best = document.querySelector('[data-qid="battle:population:campaign:best"]')?.textContent ?? ''
  const s4 = document.querySelector('[data-qid="battle:population:specimen:specimen-0004"]')?.textContent ?? ''
  const s4Target = document.querySelector('[data-qid="battle:population:specimen:specimen-0004:target"]')?.textContent ?? ''
  const runButtons = [...document.querySelectorAll('button, a')].filter((el) =>
    /^(run|execute|retry|invoke tau|approve spawn)$/i.test((el.textContent ?? '').trim()),
  )
  return {
    root: !!root,
    text,
    banners,
    specimens,
    gens,
    edges,
    mustNot,
    may,
    engine,
    notEngine,
    best,
    s4,
    s4Target,
    runButtons: runButtons.map((el) => el.textContent?.trim()),
    pixi: !!document.querySelector('[data-battle-pixi-engine]'),
    nav: !!document.querySelector('[data-qid="battle:nav:population"]'),
  }
})

record('1-population-root', proof.root, url)
record('2-population-banner', proof.banners.some((b) => /POPULATION FIXTURE/i.test(b ?? '')), JSON.stringify(proof.banners))
record('3-not-full-engine-banner', proof.banners.some((b) => /NOT FULL GENETIC ENGINE/i.test(b ?? '')), JSON.stringify(proof.banners))
record('4-judge-not-run-banner', proof.banners.some((b) => /JUDGE NOT RUN/i.test(b ?? '')), JSON.stringify(proof.banners))
record('5-exploit-not-claimed-banner', proof.banners.some((b) => /EXPLOIT SUCCESS NOT CLAIMED/i.test(b ?? '')), JSON.stringify(proof.banners))
record('6-four-specimens', proof.specimens.every((t) => t.length > 0), JSON.stringify(proof.specimens.map((t) => t.slice(0, 40))))
record('7-four-generations', proof.gens.every((t) => /Gen/i.test(t)), JSON.stringify(proof.gens))
record('8-lineage-summary', /parent-child:\s*3/i.test(proof.edges), proof.edges)
record('9-best-specimen-0004', /specimen-0004/i.test(proof.best), proof.best)
record('10-engine-false', /full_population_engine_proven\s*false/i.test(proof.engine), proof.engine)
record('11-target-unproven-best', /TARGET_CONTACT_UNPROVEN/i.test(proof.s4Target), proof.s4Target)
record('12-provider-live-false', /provider_live\s*false/i.test(proof.s4), proof.s4.slice(0, 220))
record('13-must-not-exploit', /exploit success/i.test(proof.mustNot) && !/exploit success/i.test(proof.may), JSON.stringify({ mustNot: proof.mustNot.slice(0,200), may: proof.may.slice(0,200) }))
record('14-not-full-engine-flag', /population_fixture_is_not_full_engine:\s*true/i.test(proof.notEngine), proof.notEngine)
record('15-no-tau-paths', !proof.text.includes('command-loop/command-artifacts') && !proof.text.includes('tau-dag-run/'), 'checked')
record('16-no-run-execute-button', proof.runButtons.length === 0, JSON.stringify(proof.runButtons))
record('17-no-pixi', !proof.pixi, 'pixi absent')
record('18-nav-population', proof.nav, 'nav')

await page.click('[data-qid="battle:population:generation:3"]')
await page.waitForTimeout(200)
const filtered = await page.evaluate(() => ({
  s1: !!document.querySelector('[data-qid="battle:population:specimen:specimen-0001"]'),
  s4: !!document.querySelector('[data-qid="battle:population:specimen:specimen-0004"]'),
}))
record('19-generation-filter', !filtered.s1 && filtered.s4, JSON.stringify(filtered))

await page.goto(invalidUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(() => Boolean(document.querySelector('[data-qid="battle:population:error"]')), null, { timeout: 15000 })
const invalid = await page.evaluate(() => ({
  title: document.querySelector('[data-qid="battle:population:error"]')?.textContent ?? '',
}))
record('20-invalid-fixture-fails-closed', /UNSUPPORTED FIXTURE/i.test(invalid.title), invalid.title)

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_PR5_POPULATION_PASS')
