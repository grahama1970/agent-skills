#!/usr/bin/env node
/**
 * Live Pixi proof: blue kill-shot travel → killed impact → runner death on kill fixture.
 */
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3002'
const outDir = resolve(process.env.BATTLE_KILL_SHOT_PIXI_PROOF_DIR ?? '/tmp/battle-kill-shot-pixi-proof')
const TRAVEL = 0.55
const IMPACT = 0.42

const checks = []
function record(id, pass, detail) {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

function urlFor(seconds) {
  return `${host}/#battle/receipt?engine=pixi&fixture=battle-004-kill-shot&pixiTest=1&pixiSeconds=${seconds}`
}

async function probeStage(page) {
  return page.evaluate(() => {
    const stage = document.querySelector('[data-qid="battle:pixi:stage"]')
    const anims = stage?.dataset.battleRunnerAnimations ? JSON.parse(stage.dataset.battleRunnerAnimations) : {}
    return {
      engine: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine'),
      phase: stage?.dataset.battleKillShotPhase ?? null,
      impact: stage?.dataset.battleKillShotImpact ?? null,
      lane: stage?.dataset.battleKillShotLane ?? null,
      progress: stage?.dataset.battleKillShotProgress ?? null,
      burstFrame: stage?.dataset.battleKillShotBurstFrame ?? null,
      runner: anims['payload-857-red-1'] ?? null,
    }
  })
}

async function main() {
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })

  const fixture = await (await fetch(`${host}/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json`)).json()
  const lane = fixture.lanes.find((item) => item.id === 'payload-857-red-1')
  const blastAt = lane.events.find((event) => event.kind === 'blue_blast').elapsed_seconds

  const travelAt = blastAt + TRAVEL * 0.5
  const impactAt = blastAt + TRAVEL + 0.08
  const postAt = blastAt + TRAVEL + IMPACT * 0.5

  await page.goto(urlFor(blastAt - 1), { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  const pre = await probeStage(page)
  record('pre-blast-no-kill-shot', !pre.phase && pre.engine === 'animated-sprites', JSON.stringify(pre))
  await page.screenshot({ path: resolve(outDir, '01-pre-blast.png'), fullPage: true })

  await page.goto(urlFor(travelAt), { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForTimeout(1200)
  const travel = await probeStage(page)
  record(
    'kill-shot-travel-beam',
    travel.phase === 'travel' && travel.lane === 'payload-857-red-1' && Number(travel.progress) > 40,
    JSON.stringify(travel),
  )
  record('runner-advances-during-travel', travel.runner === 'walk' || travel.runner === 'run', JSON.stringify(travel))
  await page.screenshot({ path: resolve(outDir, '02-travel-beam.png'), fullPage: true })

  await page.goto(urlFor(impactAt), { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForTimeout(1200)
  const impact = await probeStage(page)
  record(
    'kill-shot-impact-killed',
    impact.phase === 'impact' && impact.impact === 'killed' && impact.runner === 'killed' && impact.burstFrame != null,
    JSON.stringify(impact),
  )
  await page.screenshot({ path: resolve(outDir, '03-impact-killed.png'), fullPage: true })

  await page.goto(urlFor(postAt), { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForTimeout(1200)
  const post = await probeStage(page)
  record('runner-holds-killed-after-impact', post.runner === 'killed', JSON.stringify(post))
  await page.screenshot({ path: resolve(outDir, '04-post-impact-killed.png'), fullPage: true })

  await browser.close()
  if (errors.length) record('page-errors', false, errors.slice(0, 3).join(' | '))

  const failed = checks.filter((check) => !check.pass)
  console.log(JSON.stringify({ checks, outDir, failed: failed.length }, null, 2))
  if (failed.length) process.exit(1)
  console.log('BATTLE_PROVE_KILL_SHOT_PIXI_PASS')
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
