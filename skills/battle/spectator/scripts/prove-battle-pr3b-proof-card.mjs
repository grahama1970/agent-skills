#!/usr/bin/env node
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const url = `${host}/#battle/proof?fixture=battle-004-pr3b`
const invalidUrl = `${host}/#battle/proof?fixture=not-a-registered-fixture`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1400 } })

await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:proof-card:root"]', { timeout: 20000 })

const proof = await page.evaluate(() => {
  const root = document.querySelector('[data-qid="battle:proof-card:root"]')
  const text = root?.textContent ?? ''
  const passNodes = ['lineage-summarizer', 'research-scout', 'method-combiner']
    .map((id) => document.querySelector(`[data-qid="battle:proof-card:node:${id}"]`)?.textContent ?? '')
  const author = document.querySelector('[data-qid="battle:proof-card:node:exploit-code-author"]')?.textContent ?? ''
  const external = document.querySelector('[data-qid="battle:proof-card:research:external-tool"]')?.textContent ?? ''
  const provider = document.querySelector('[data-qid="battle:proof-card:research:provider-live"]')?.textContent ?? ''
  const methods = document.querySelector('[data-qid="battle:proof-card:methods"]')?.textContent ?? ''
  const deferred = document.querySelector('[data-qid="battle:proof-card:genome:deferred"]')?.textContent ?? ''
  const notCode = document.querySelector('[data-qid="battle:proof-card:genome:not-code"]')?.textContent ?? ''
  const mustNot = document.querySelector('[data-qid="battle:proof-card:claim-must-not"]')?.textContent ?? ''
  const may = document.querySelector('[data-qid="battle:proof-card:claim-may"]')?.textContent ?? ''
  const runButtons = [...document.querySelectorAll('button, a')].filter((el) =>
    /^(run|execute|retry|invoke tau|approve spawn)$/i.test((el.textContent ?? '').trim()),
  )
  return {
    root: !!root,
    text,
    passNodes,
    author,
    external,
    provider,
    methods,
    deferred,
    notCode,
    mustNot,
    may,
    runButtons: runButtons.map((el) => el.textContent?.trim()),
    headline: document.querySelector('[data-qid="battle:proof-card:headline"]')?.textContent?.trim() ?? '',
    boundaryExternal: document.querySelector('[data-qid="battle:proof-card:boundary:external-tool"]')?.textContent ?? '',
    boundaryProvider: document.querySelector('[data-qid="battle:proof-card:boundary:provider-live"]')?.textContent ?? '',
    boundaryCode: document.querySelector('[data-qid="battle:proof-card:boundary:exploit-code-generated"]')?.textContent ?? '',
  }
})

record('1-proof-card-root', proof.root, url)
record('2-three-pass-nodes', proof.passNodes.every((t) => /PASS/i.test(t)), JSON.stringify(proof.passNodes))
record('3-exploit-code-author-blocked', /BLOCKED/i.test(proof.author), proof.author)
record('4-external-tool-called-false', /External research tool called\s*No/i.test(proof.external), proof.external)
record('5-provider-live-false', /Provider\/model called\s*No/i.test(proof.provider), proof.provider)
record('6-selected-methods-visible', /Archive traversal baseline|Child archive traversal baseline/i.test(proof.methods), proof.methods.slice(0, 240))
record('7-rejected-deferred-visible', /MITM|assembly|drop_mitm/i.test(proof.deferred + proof.methods), (proof.deferred + proof.methods).slice(0, 240))
record('8-not-exploit-code-copy', /NOT EXPLOIT CODE/i.test(proof.notCode), proof.notCode)
record('9-exploit-success-only-in-does-not-prove', /exploit success/i.test(proof.mustNot) && !/exploit success/i.test(proof.may) && !/exploit success/i.test(proof.headline), JSON.stringify({ mustNot: proof.mustNot, may: proof.may, headline: proof.headline }))
record('10-no-tau-command-loop-paths', !proof.text.includes('command-loop/command-artifacts'), 'checked root text')
record('11-no-run-execute-button', proof.runButtons.length === 0, JSON.stringify(proof.runButtons))
record('11b-execution-boundary', /external_tool_called\s*false/i.test(proof.boundaryExternal) && /provider_live\s*false/i.test(proof.boundaryProvider) && /exploit code generated\s*false/i.test(proof.boundaryCode), JSON.stringify({ external: proof.boundaryExternal, provider: proof.boundaryProvider, code: proof.boundaryCode }))

await page.goto(invalidUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(() => Boolean(document.querySelector('[data-qid="battle:proof-card:error"]')), null, { timeout: 15000 })
const invalid = await page.evaluate(() => ({
  title: document.querySelector('[data-qid="battle:proof-card:error"]')?.textContent ?? '',
}))
record('12-invalid-fixture-fails-closed', /UNSUPPORTED FIXTURE/i.test(invalid.title), invalid.title)

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_PR3B_PROOF_CARD_PASS')
