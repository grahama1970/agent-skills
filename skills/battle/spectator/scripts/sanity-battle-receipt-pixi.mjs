#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const fixtureId = process.env.BATTLE_RECEIPT_FIXTURE ?? 'battle-004-adaptive-lineage-v13'
const baseUrl = process.env.BATTLE_RECEIPT_URL ?? `${host}/#battle/receipt?engine=pixi&fixture=${fixtureId}`
const outDir = resolve(process.env.BATTLE_RECEIPT_CAPTURE_DIR ?? '/tmp/battle-receipt-pixi-sanity')
const spawnAtOverride = Number(process.env.BATTLE_RECEIPT_SPAWN_SECONDS ?? 'NaN')

function laneId(lane) {
  return lane?.lane_id ?? lane?.id ?? null
}

function parentLaneId(lane) {
  return lane?.parent_lane_id ?? lane?.parent_id ?? null
}

async function loadFixtureContract() {
  const fixtureUrl = `${host}/battle-fixtures/${fixtureId}/battle.normalized_ux_fixture.json`
  const response = await fetch(fixtureUrl)
  if (!response.ok) {
    throw new Error(`fixture ${fixtureId} unavailable over HTTP: ${response.status}`)
  }
  const fixtureText = await response.text()
  const fixtureSha256 = createHash('sha256').update(fixtureText).digest('hex')
  const fixture = JSON.parse(fixtureText)
  const lanes = Array.isArray(fixture.lanes) ? fixture.lanes : []
  const parents = lanes.map(laneId).filter((id, index) => id && !parentLaneId(lanes[index]))
  const children = lanes.map(laneId).filter((id, index) => id && parentLaneId(lanes[index]))
  const firstEdgeTime = Array.isArray(fixture.lineage_edges)
    ? Math.min(...fixture.lineage_edges.map((edge) => Number(edge.visible_from_elapsed_seconds)).filter(Number.isFinite))
    : NaN
  const firstChildVisible = Math.min(...lanes.map((lane) => Number(lane.visible_from_elapsed_seconds ?? lane.spawn_time_seconds)).filter((value) => Number.isFinite(value) && value > 0))
  const spawnAt = Number.isFinite(spawnAtOverride)
    ? spawnAtOverride
    : Number.isFinite(firstEdgeTime)
      ? firstEdgeTime
      : firstChildVisible

  if (!parents.length || !children.length || !Number.isFinite(spawnAt)) {
    throw new Error(`fixture ${fixtureId} lacks a parent/child spawn contract`)
  }
  return {
    schema: fixture.schema,
    battle_id: fixture.battle_id,
    run_id: fixture.run_id ?? null,
    parents,
    children,
    spawnAt,
    fixture_id: fixture.fixture_id ?? fixtureId,
    source_proof_id: fixture.provenance?.source_proof_id ?? fixture.source_proof_id ?? null,
    source_fixture_url: fixtureUrl,
    source_fixture_sha256: fixture.source_fixture_sha256 ?? fixtureSha256,
    fetched_fixture_sha256: fixtureSha256,
  }
}

function hasLane(laneIds, id) {
  return laneIds.includes(`battle:lane:${id}`)
}

async function main() {
  const contract = await loadFixtureContract()
  const parentId = contract.parents[0]
  const childId = contract.children[0]
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForTimeout(2000)

  const beforeSpawn = await page.evaluate(() => ({
    source: {
      battle_id: document.querySelector('[data-qid="battle:race:source"]')?.getAttribute('data-battle-id') ?? null,
      run_id: document.querySelector('[data-qid="battle:race:source"]')?.getAttribute('data-run-id') ?? null,
      source_proof_id: document.querySelector('[data-qid="battle:race:source"]')?.getAttribute('data-source-proof-id') ?? null,
      source_fixture_id: document.querySelector('[data-qid="battle:race:source"]')?.getAttribute('data-source-fixture-id') ?? null,
      source_fixture_sha256: document.querySelector('[data-qid="battle:race:source"]')?.getAttribute('data-source-fixture-sha256') ?? null,
    },
    lanes: [...document.querySelectorAll('[data-qid^="battle:lane:"]')].map((el) => el.getAttribute('data-qid')),
  }))

  await page.goto(`${baseUrl}${baseUrl.includes('?') ? '&' : '?'}pixiTest=1&pixiSeconds=${Math.max(0, contract.spawnAt - 5)}`, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForTimeout(2500)
  const pre = await page.evaluate(() => ({
    lanes: [...document.querySelectorAll('[data-qid^="battle:lane:"]')].map((el) => el.getAttribute('data-qid')),
  }))
  await page.screenshot({ path: resolve(outDir, 'before-spawn.png') })

  await page.goto(`${baseUrl}${baseUrl.includes('?') ? '&' : '?'}pixiTest=1&pixiSeconds=${contract.spawnAt + 5}`, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForTimeout(2500)
  const post = await page.evaluate(() => ({
    lanes: [...document.querySelectorAll('[data-qid^="battle:lane:"]')].map((el) => el.getAttribute('data-qid')),
  }))
  await page.screenshot({ path: resolve(outDir, 'after-spawn.png') })

  // scrub test on receipt route
  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForTimeout(2000)
  const labelBefore = await page.textContent('.playheadLabel')
  const track = page.locator('[data-qid="battle:timeline:scrub"]')
  const box = await track.boundingBox()
  if (box) await track.click({ position: { x: box.width * 0.2, y: box.height / 2 } })
  await page.waitForTimeout(400)
  const labelAfter = await page.textContent('.playheadLabel')

  await browser.close()

  if (errors.length) {
    console.error(errors.slice(0, 5).join('\n'))
    process.exit(1)
  }
  if (!hasLane(pre.lanes, parentId) || hasLane(pre.lanes, childId)) {
    console.error('child visible before spawn', { contract, pre })
    process.exit(1)
  }
  if (!hasLane(post.lanes, parentId) || !hasLane(post.lanes, childId)) {
    console.error('child missing after spawn', { contract, post })
    process.exit(1)
  }
  if (labelBefore === labelAfter) {
    console.error('scrub did not move playhead', { labelBefore, labelAfter })
    process.exit(1)
  }

  console.log('PASS battle-receipt-pixi-sanity')
  console.log(JSON.stringify({ route: { url: baseUrl }, fixture: contract, loadedSource: beforeSpawn.source, beforeSpawn, pre, post, scrub: { labelBefore, labelAfter }, screenshots: outDir }, null, 2))
}

main().catch((error) => { console.error(error); process.exit(1) })
