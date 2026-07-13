#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3003'
const outDir = resolve(process.env.BATTLE_ADAPTIVE_V13_PROOF_DIR ?? '/tmp/battle-adaptive-lineage-v13-proof')
const baseUrl = `${host}/#battle/receipt?engine=pixi&fixture=battle-004-adaptive-lineage-v13&pixiTest=1&reducedMotion=1&particles=0`
const checks = []
const errors = []
const requests = new Set()
const authorityRequests = new Set()
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${JSON.stringify(detail)}`)
}

await mkdir(outDir, { recursive: true })
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(message.text())
})
page.on('request', (request) => {
  requests.add(request.url())
  if (['fetch', 'xhr', 'image', 'media'].includes(request.resourceType())) {
    authorityRequests.add(request.url())
  }
})

const fixtureResponse = await fetch(`${host}/battle-fixtures/battle-004-adaptive-lineage-v13/battle.normalized_ux_fixture.json`)
const fixture = await fixtureResponse.json()
record('fixture-http', fixtureResponse.ok && fixture.schema === 'battle.normalized_adaptive_lineage_fixture.v1', { status: fixtureResponse.status, schema: fixture.schema })
record('fixture-causal-contract', fixture.causal_continuity_proven === true && fixture.events?.length === 24 && fixture.lanes?.length === 4 && fixture.lineage_edges?.length === 2, { causal: fixture.causal_continuity_proven, events: fixture.events?.length, lanes: fixture.lanes?.length, edges: fixture.lineage_edges?.length })
record('fixture-shared-atlas', fixture.sprite_theme?.shared_atlas === true && fixture.sprite_theme?.semantic_authority === false && fixture.sprite_theme?.variants?.['v13-shared-runner']?.sprite_id === 'plague_nurgling', fixture.sprite_theme)

async function inspectAt(seconds, name, viewport = { width: 1600, height: 1050 }) {
  await page.setViewportSize(viewport)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto(`${baseUrl}&pixiSeconds=${seconds}`, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForSelector('canvas.pixiRaceCanvas', { timeout: 20_000 })
  await page.waitForTimeout(900)
  const scroller = page.locator('[data-qid="battle:timeline:scroll"]')
  if (viewport.width < 700) await scroller.evaluate(async (node) => {
    let prior = node.scrollLeft
    let stableFrames = 0
    for (let frame = 0; frame < 120; frame += 1) {
      await new Promise(requestAnimationFrame)
      const current = node.scrollLeft
      stableFrames = Math.abs(current - prior) <= 0.5 ? stableFrames + 1 : 0
      prior = current
      if (stableFrames >= 4) return
    }
    throw new Error('Mobile timeline scroll did not stabilize')
  })
  const state = await page.evaluate(() => {
    const stage = document.querySelector('[data-qid="battle:pixi:stage"]')
    const canvas = document.querySelector('canvas.pixiRaceCanvas')
    const box = canvas?.getBoundingClientRect()
    return {
      laneIds: [...document.querySelectorAll('[data-lane-id]')].map((element) => element.getAttribute('data-lane-id')).filter(Boolean),
      laneText: [...document.querySelectorAll('[data-lane-id]')].map((element) => element.textContent?.replace(/\s+/g, ' ').trim()),
      animations: JSON.parse(stage?.dataset.battleRunnerAnimations ?? '{}'),
      lineagePhases: JSON.parse(stage?.dataset.battleLineagePhases ?? '{}'),
      canvas: { width: box?.width ?? 0, height: box?.height ?? 0 },
      pageWidth: { client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth },
      timelineScrollLeft: document.querySelector('.battle-timeline-scroll')?.scrollLeft ?? 0,
      body: document.body.textContent ?? '',
    }
  })
  const screenshot = resolve(outDir, name)
  await page.screenshot({ path: screenshot, fullPage: viewport.width >= 700, animations: 'disabled', caret: 'hide', scale: 'css' })
  let raceScreenshot = null
  if (viewport.width < 700) {
    raceScreenshot = resolve(outDir, '08-four-lane-mobile-race.png')
    await scroller.screenshot({ path: raceScreenshot, animations: 'disabled', caret: 'hide', scale: 'css' })
  }
  return { ...state, screenshot, raceScreenshot }
}

const preSpawn = await inspectAt(71.67, '01-pre-spawn-children-hidden.png')
record('pre-spawn-parent-only', JSON.stringify([...new Set(preSpawn.laneIds)].sort()) === JSON.stringify(['blue-g1', 'red-g1']), preSpawn)

const pending = await inspectAt(72, '02-spawn-authorized-pending.png')
record('authorized-four-lanes', ['red-g1', 'red-g2', 'blue-g1', 'blue-g2'].every((id) => pending.laneIds.includes(id)), pending.laneIds)
record('authorized-pending-not-active', pending.lineagePhases['red-g2'] === 'authorized_pending' && pending.lineagePhases['blue-g2'] === 'authorized_pending' && pending.animations['red-g2'] === 'idle' && pending.animations['blue-g2'] === 'idle' && /AUTHORIZED PENDING/.test(pending.body), pending)

const descending = await inspectAt(79.2, '03-ladder-descent-hop.png')
record('research-materializes-child', descending.lineagePhases['red-g2'] === 'descending' && descending.lineagePhases['blue-g2'] === 'descending' && descending.animations['red-g2'] === 'spawn' && descending.animations['blue-g2'] === 'spawn', descending)

const active = await inspectAt(82, '04-children-active-research.png')
record('children-active-research', active.lineagePhases['red-g2'] === 'active' && active.lineagePhases['blue-g2'] === 'active' && active.animations['red-g2'] === 'research' && active.animations['blue-g2'] === 'research', active)

const mutation = await inspectAt(134.451, '05-mutation-evidence.png')
record('mutation-evidence-animation', mutation.animations['red-g2'] === 'mutate' && mutation.animations['blue-g2'] === 'mutate' && /MUTATION EVIDENCE VERIFIED/.test(mutation.body), mutation)

const finalState = await inspectAt(134.457, '06-judge-selection-memory-boundary.png')
record('no-terminal-overclaim', Object.values(finalState.animations).every((value) => !['killed', 'victory', 'promoted'].includes(value)), finalState.animations)
record('canvas-nonblank-dimensions', finalState.canvas.width > 900 && finalState.canvas.height > 200, finalState.canvas)

const mobile = await inspectAt(129, '07-four-lane-mobile.png', { width: 430, height: 900 })
record('mobile-four-lane-state', ['red-g1', 'red-g2', 'blue-g1', 'blue-g2'].every((id) => mobile.laneIds.includes(id)) && mobile.canvas.width > 300 && mobile.pageWidth.scroll <= mobile.pageWidth.client && mobile.timelineScrollLeft > 0, mobile)

const requestList = [...requests]
const authorityRequestList = [...authorityRequests]
record('plague-atlas-requested', requestList.some((url) => /plague_nurgling\.json/.test(url)) && requestList.some((url) => /plague_nurgling\.png/.test(url)), requestList.filter((url) => /plague_nurgling/.test(url)))
record('no-raw-runtime-requests', authorityRequestList.every((url) => !/\/tmp\/|tau-live|provider-workspace|arena\/private|command-loop/.test(url)), authorityRequestList.filter((url) => /\/tmp\/|tau-live|provider-workspace|arena\/private|command-loop/.test(url)))
record('no-browser-errors', errors.length === 0, errors)

await browser.close()
const failed = checks.filter((check) => !check.pass)
const report = { pass: failed.length === 0, mocked: false, live: true, host, route: baseUrl, fixture: { event_count: fixture.events?.length, lane_count: fixture.lanes?.length, lineage_edge_count: fixture.lineage_edges?.length }, checks, failed: failed.map((check) => check.id), errors, requests: requestList, authority_requests: authorityRequestList, screenshots: outDir }
await writeFile(resolve(outDir, 'summary.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(report, null, 2))
process.exit(report.pass ? 0 : 1)
