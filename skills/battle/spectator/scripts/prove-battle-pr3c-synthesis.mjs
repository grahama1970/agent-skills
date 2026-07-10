#!/usr/bin/env node
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const url = `${host}/#battle/synthesis?fixture=battle-004-pr3c`
const invalidUrl = `${host}/#battle/synthesis?fixture=not-a-registered-fixture`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1600 } })

await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:synthesis:root"]', { timeout: 20000 })

const synth = await page.evaluate(() => {
  const root = document.querySelector('[data-qid="battle:synthesis:root"]')
  const text = root?.textContent ?? ''
  const passNodes = ['lineage-summarizer', 'research-scout', 'method-combiner', 'exploit-code-author']
    .map((id) => document.querySelector(`[data-qid="battle:synthesis:node:${id}"]`)?.textContent ?? '')
  const banners = [...document.querySelectorAll('[data-qid^="battle:synthesis:banner:"]')].map((el) => el.textContent?.trim())
  const mustNot = document.querySelector('[data-qid="battle:synthesis:claim-must-not"]')?.textContent ?? ''
  const may = document.querySelector('[data-qid="battle:synthesis:claim-may"]')?.textContent ?? ''
  const code = document.querySelector('[data-qid="battle:synthesis:code:preview"]')?.textContent ?? ''
  const provider = document.querySelector('[data-qid="battle:synthesis:authorship:provider"]')?.textContent ?? ''
  const model = document.querySelector('[data-qid="battle:synthesis:authorship:model"]')?.textContent ?? ''
  const providerLive = document.querySelector('[data-qid="battle:synthesis:authorship:provider-live"]')?.textContent ?? ''
  const compile = document.querySelector('[data-qid="battle:synthesis:boundary:compile_status"]')?.textContent ?? ''
  const runtime = document.querySelector('[data-qid="battle:synthesis:boundary:runtime_status"]')?.textContent ?? ''
  const judge = document.querySelector('[data-qid="battle:synthesis:boundary:judge_status"]')?.textContent ?? ''
  const runButtons = [...document.querySelectorAll('button, a')].filter((el) =>
    /^(run|execute|retry|invoke tau|approve spawn|compile)$/i.test((el.textContent ?? '').trim()),
  )
  return {
    root: !!root,
    text,
    passNodes,
    banners,
    mustNot,
    may,
    code: code.slice(0, 240),
    codeLen: code.length,
    provider,
    model,
    providerLive,
    compile,
    runtime,
    judge,
    runButtons: runButtons.map((el) => el.textContent?.trim()),
    headline: document.querySelector('[data-qid="battle:synthesis:headline"]')?.textContent?.trim() ?? '',
    pixi: !!document.querySelector('[data-battle-pixi-engine]'),
    nav: !!document.querySelector('[data-qid="battle:nav:synthesis"]'),
  }
})

record('1-synthesis-root', synth.root, url)
record('2-four-pass-nodes', synth.passNodes.every((t) => /PASS/i.test(t)), JSON.stringify(synth.passNodes))
record('3-provider-authored-banner', synth.banners.some((b) => /PROVIDER-AUTHORED SPECIMEN/i.test(b ?? '')), JSON.stringify(synth.banners))
record('4-not-compiled-banner', synth.banners.some((b) => /NOT COMPILED/i.test(b ?? '')), JSON.stringify(synth.banners))
record('5-not-executed-banner', synth.banners.some((b) => /NOT EXECUTED/i.test(b ?? '')), JSON.stringify(synth.banners))
record('6-not-judge-banner', synth.banners.some((b) => /NOT JUDGE VERIFIED/i.test(b ?? '')), JSON.stringify(synth.banners))
record('7-provider-live-true', /provider_live\s*true/i.test(synth.providerLive), synth.providerLive)
record('8-observed-provider-model', /opencode-go/i.test(synth.provider) && /kimi/i.test(synth.model), JSON.stringify({ provider: synth.provider, model: synth.model }))
record('9-code-preview-present', synth.codeLen > 40 && /python|exploit|archive/i.test(synth.code), synth.code)
record('10-execution-boundary-not-run', /NOT_RUN/i.test(synth.compile) && /NOT_RUN/i.test(synth.runtime) && /NOT_RUN/i.test(synth.judge), JSON.stringify({ compile: synth.compile, runtime: synth.runtime, judge: synth.judge }))
record('11-must-not-claim-compile-runtime', /compiled|compile passed|runtime success|exploit success|judge success/i.test(synth.mustNot), synth.mustNot.slice(0, 280))
record('12-no-overclaim-in-may', !/compile passed|runtime success|exploit success|judge success/i.test(synth.may), synth.may.slice(0, 280))
record('13-no-tau-command-loop-paths', !synth.text.includes('command-loop/command-artifacts') && !synth.text.includes('tau-dag-run/'), 'checked root text')
record('14-no-run-execute-compile-button', synth.runButtons.length === 0, JSON.stringify(synth.runButtons))
record('15-no-pixi-on-synthesis', !synth.pixi, 'pixi absent')
record('16-nav-synthesis-link', synth.nav, 'nav present')

await page.goto(invalidUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(() => Boolean(document.querySelector('[data-qid="battle:synthesis:error"]')), null, { timeout: 15000 })
const invalid = await page.evaluate(() => ({
  title: document.querySelector('[data-qid="battle:synthesis:error"]')?.textContent ?? '',
}))
record('17-invalid-fixture-fails-closed', /UNSUPPORTED FIXTURE/i.test(invalid.title), invalid.title)

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_PR3C_SYNTHESIS_PASS')
