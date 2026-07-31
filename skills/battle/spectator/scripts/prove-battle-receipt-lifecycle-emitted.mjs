#!/usr/bin/env node
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const url = `${host}/#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn-lifecycle`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

async function lifecycleField(page, field) {
  return page.evaluate((name) => {
    const root = document.querySelector('[data-qid="battle:agent-pane:lifecycle-evidence"]')
    return root?.querySelector(`[data-battle-lifecycle-field="${name}"]`)?.textContent?.trim() ?? ''
  }, field)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 })

const fixtureMeta = await page.evaluate(async () => {
  const response = await fetch('/battle-fixtures/battle-004-parent-spawn-lifecycle-pixi-replay/battle.normalized_ux_fixture.json')
  const fixture = await response.json()
  return {
    ok: response.ok,
    fieldsEmitted: fixture.lifecycle_enrichment?.fields_emitted ?? [],
  }
})
const emitted = new Set(Array.isArray(fixtureMeta.fieldsEmitted) ? fixtureMeta.fieldsEmitted : [])

function fieldIsFailClosed(text) {
  return text.includes('not emitted') || text.includes('not promoted') || text.includes('false')
}

function fieldMatchesContract(field, text, predicate) {
  return emitted.has(field) ? predicate(text) : fieldIsFailClosed(text)
}

await page.locator('[data-qid="battle:lane:payload-857-red-1"]').first().click({ timeout: 10000 })
await page.waitForSelector('[data-qid="battle:agent-pane:lifecycle-evidence"]', { timeout: 10000 })

const childKnowledge = await lifecycleField(page, 'knowledge_packet')
const childMemory = await lifecycleField(page, 'memory_promotion')
const childScore = await lifecycleField(page, 'score_calibration')
const childNetwork = await lifecycleField(page, 'network_summary.available')

record('0-fixture-lifecycle-contract-loaded', fixtureMeta.ok && emitted.has('score_calibration'), JSON.stringify(fixtureMeta))
record('1-child-knowledge-packet-contract', fieldMatchesContract('knowledge_packet', childKnowledge, (text) => text.includes('inherited') && !text.includes('not emitted')), childKnowledge)
record('2-child-memory-promotion-contract', fieldMatchesContract('memory_promotion', childMemory, (text) => text.includes('not promoted') && !text.includes('not emitted')), childMemory)
record('3-child-score-calibration-emitted', childScore.length > 0 && !childScore.includes('not emitted'), childScore)
record('4-child-network-summary-honest', fieldMatchesContract('network_summary', childNetwork, (text) => text.includes('false')), childNetwork)

await page.locator('[data-qid="battle:lane:payload-857-receipt"]').first().click({ timeout: 10000 })
await page.waitForTimeout(400)

const parentSpawn = await lifecycleField(page, 'spawn_request')
const parentTau = await lifecycleField(page, 'tau_branch_decision')
const parentKnowledge = await lifecycleField(page, 'knowledge_packet')
const parentScore = await lifecycleField(page, 'score_calibration')

record('5-parent-spawn-request-contract', fieldMatchesContract('spawn_request', parentSpawn, (text) => text.length > 0 && !text.includes('not emitted')), parentSpawn)
record('6-parent-tau-branch-contract', fieldMatchesContract('tau_branch_decision', parentTau, (text) => text.length > 0 && !text.includes('not emitted')), parentTau)
record('7-parent-knowledge-packet-contract', fieldMatchesContract('knowledge_packet', parentKnowledge, (text) => text.includes('materialized') && !text.includes('not emitted')), parentKnowledge)
record('8-parent-score-calibration-emitted', parentScore.length > 0 && !parentScore.includes('not emitted'), parentScore)

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_RECEIPT_LIFECYCLE_EMITTED_PASS')
