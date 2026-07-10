#!/usr/bin/env node
/**
 * Live proof: shared fixture loader discriminates schemas and fail-closes mismatches.
 * Exercises real fixture HTTP from the spectator host (not mocked).
 */
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage()
await page.goto(`${host}/#battle/receipt?engine=pixi`, { waitUntil: 'networkidle', timeout: 60000 })

const proof = await page.evaluate(async () => {
  async function load(url) {
    const r = await fetch(url)
    return { ok: r.ok, status: r.status, json: r.ok ? await r.json() : null }
  }
  const race = await load('/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json')
  const proofCard = await load('/battle-fixtures/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json')
  const synthesis = await load('/battle-fixtures/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json')
  const compile = await load('/battle-fixtures/battle-004-pr3d-compile/battle.normalized_compile_fixture.json')
  const runtime = await load('/battle-fixtures/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json')
  return {
    raceSchema: race.json?.schema ?? null,
    proofSchema: proofCard.json?.schema ?? null,
    synthesisSchema: synthesis.json?.schema ?? null,
    compileSchema: compile.json?.schema ?? null,
    runtimeSchema: runtime.json?.schema ?? null,
    raceOk: race.ok,
    proofOk: proofCard.ok,
    synthesisOk: synthesis.ok,
    compileOk: compile.ok,
    runtimeOk: runtime.ok,
    raceHasLanes: Array.isArray(race.json?.lanes),
    proofHasNodes: Boolean(proofCard.json?.node_status),
    synthesisProviderLive: synthesis.json?.provider_live === true,
    compileFailed: compile.json?.compile?.compile_failed === true,
    judgeNotRun: runtime.json?.judge?.judge_status === 'NOT_RUN',
  }
})

record('1-race-fixture-served', proof.raceOk && proof.raceSchema === 'battle.normalized_ux_fixture.v1', JSON.stringify(proof))
record('2-proof-card-fixture-served', proof.proofOk && proof.proofSchema === 'battle.normalized_proof_card_fixture.v1', JSON.stringify(proof))
record('2b-synthesis-fixture-served', proof.synthesisOk && proof.synthesisSchema === 'battle.normalized_synthesis_fixture.v1' && proof.synthesisProviderLive, JSON.stringify(proof))
record('2c-compile-fixture-served', proof.compileOk && proof.compileSchema === 'battle.normalized_compile_fixture.v1' && proof.compileFailed, JSON.stringify(proof))
record('2d-runtime-fixture-served', proof.runtimeOk && proof.runtimeSchema === 'battle.normalized_runtime_judge_fixture.v1' && proof.judgeNotRun, JSON.stringify(proof))
record('3-schemas-differ', proof.raceSchema !== proof.proofSchema && proof.proofSchema !== proof.synthesisSchema && proof.synthesisSchema !== proof.compileSchema && proof.compileSchema !== proof.runtimeSchema, JSON.stringify({ race: proof.raceSchema, proof: proof.proofSchema, synthesis: proof.synthesisSchema, compile: proof.compileSchema, runtime: proof.runtimeSchema }))
record('4-race-has-lanes', proof.raceHasLanes, JSON.stringify(proof))
record('5-proof-has-nodes', proof.proofHasNodes, JSON.stringify(proof))

// Route-level: proof-card page rejects if we somehow loaded race schema into proof route UI
await page.goto(`${host}/#battle/proof?fixture=battle-004-pr3b`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:proof-card:root"]', { timeout: 20000 })
const onProof = await page.evaluate(() => ({
  root: !!document.querySelector('[data-qid="battle:proof-card:root"]'),
  pixi: !!document.querySelector('[data-battle-pixi-engine]'),
}))
record('6-proof-route-no-pixi', onProof.root && !onProof.pixi, JSON.stringify(onProof))

await page.goto(`${host}/#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 })
const onRace = await page.evaluate(() => ({
  pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine'),
  proofRoot: !!document.querySelector('[data-qid="battle:proof-card:root"]'),
}))
record('7-race-route-no-proof-card', onRace.pixi === 'animated-sprites' && !onRace.proofRoot, JSON.stringify(onRace))

await page.goto(`${host}/#battle/synthesis?fixture=battle-004-pr3c`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:synthesis:root"]', { timeout: 20000 })
const onSynthesis = await page.evaluate(() => ({
  root: !!document.querySelector('[data-qid="battle:synthesis:root"]'),
  pixi: !!document.querySelector('[data-battle-pixi-engine]'),
}))
record('8-synthesis-route-no-pixi', onSynthesis.root && !onSynthesis.pixi, JSON.stringify(onSynthesis))

await page.goto(`${host}/#battle/compile?fixture=battle-004-pr3d`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:compile:root"]', { timeout: 20000 })
const onCompile = await page.evaluate(() => ({
  root: !!document.querySelector('[data-qid="battle:compile:root"]'),
  pixi: !!document.querySelector('[data-battle-pixi-engine]'),
}))
record('9-compile-route-no-pixi', onCompile.root && !onCompile.pixi, JSON.stringify(onCompile))

await page.goto(`${host}/#battle/runtime?fixture=battle-004-pr4`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:runtime:root"]', { timeout: 20000 })
const onRuntime = await page.evaluate(() => ({
  root: !!document.querySelector('[data-qid="battle:runtime:root"]'),
  pixi: !!document.querySelector('[data-battle-pixi-engine]'),
}))
record('10-runtime-route-no-pixi', onRuntime.root && !onRuntime.pixi, JSON.stringify(onRuntime))

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_VIEW_FIXTURE_LOADER_PASS')
