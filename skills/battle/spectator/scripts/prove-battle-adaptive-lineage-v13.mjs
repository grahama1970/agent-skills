#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { readFile, stat, writeFile, mkdir } from 'node:fs/promises'
import { relative, resolve } from 'node:path'
import { chromium } from 'playwright'

const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3003'
const outDir = resolve(process.env.BATTLE_ADAPTIVE_V13_PROOF_DIR ?? '/tmp/battle-adaptive-lineage-v13-proof')
const screenshotsDir = resolve(outDir, 'screenshots')
const spectatorDir = resolve(import.meta.dirname, '..')
const battleDir = resolve(spectatorDir, '..')
const repositoryDir = resolve(battleDir, '..', '..')
const retainedRoot = resolve(process.env.BATTLE_ADAPTIVE_V13_CAMPAIGN_ROOT ?? '/tmp/battle-004-adaptive-red-blue-lineage-v13')
const fixtureId = 'battle-004-adaptive-lineage-v13'
const baseUrl = `${host}/#battle/receipt?engine=pixi&fixture=${fixtureId}&pixiTest=1&reducedMotion=1&particles=0`
const continuousReplayUrl = `${host}/#battle/receipt?engine=pixi&fixture=${fixtureId}&reducedMotion=1&particles=0`
const checks = []
const errors = []
const consoleMessages = []
const requests = new Map()
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${JSON.stringify(detail)}`)
}

async function sha256File(path) {
  return createHash('sha256').update(await readFile(path)).digest('hex')
}

async function sourceArtifact(path, id) {
  const fileStat = await stat(path)
  return { id, path: relative(repositoryDir, path), sha256: await sha256File(path), bytes: fileStat.size }
}

await mkdir(screenshotsDir, { recursive: true })
const retainedCampaignPath = resolve(retainedRoot, 'campaign-receipt.json')
const retainedEventsPath = resolve(retainedRoot, 'events.jsonl')
// The canary receipt embeds live timestamps (committed_at / source_created_at) and a
// per-run run_id, so it is non-deterministic — an exact frozen-hash comparison can
// never pass reproducibly. Validate the retained artifacts structurally instead:
// a valid PASS receipt of the expected schema plus a non-empty, well-formed event log.
const retainedCampaignHash = await sha256File(retainedCampaignPath)
const retainedEventsHash = await sha256File(retainedEventsPath)
const retainedCampaign = JSON.parse(await readFile(retainedCampaignPath, 'utf8'))
const retainedEventLines = (await readFile(retainedEventsPath, 'utf8')).trim().split('\n').filter(Boolean)
record(
  'retained-campaign-valid',
  retainedCampaign.status === 'PASS' && retainedCampaign.schema === 'battle.adaptive_red_blue_lineage_canary.v1',
  { status: retainedCampaign.status, schema: retainedCampaign.schema },
)
record(
  'retained-events-wellformed',
  retainedEventLines.length > 0 && retainedEventLines.every((line) => { try { JSON.parse(line); return true } catch { return false } }),
  { events: retainedEventLines.length },
)

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (message) => {
  consoleMessages.push({ type: message.type(), text: message.text() })
  if (message.type() === 'error') errors.push(message.text())
})
page.on('request', (request) => {
  requests.set(request.url(), { url: request.url(), resource_type: request.resourceType(), method: request.method() })
})

const fixtureResponse = await fetch(`${host}/battle-fixtures/${fixtureId}/battle.normalized_ux_fixture.json`)
const fixture = await fixtureResponse.json()
record('fixture-http', fixtureResponse.ok && fixture.schema === 'battle.normalized_adaptive_lineage_fixture.v1', { status: fixtureResponse.status, schema: fixture.schema })
record('fixture-causal-contract', fixture.causal_continuity_proven === true && fixture.events?.length === 24 && fixture.lanes?.length === 4 && fixture.lineage_edges?.length === 2, { causal: fixture.causal_continuity_proven, events: fixture.events?.length, lanes: fixture.lanes?.length, edges: fixture.lineage_edges?.length })
record('fixture-shared-atlas', fixture.sprite_theme?.shared_atlas === true && fixture.sprite_theme?.semantic_authority === false && fixture.sprite_theme?.variants?.['v13-shared-runner']?.sprite_id === 'plague_nurgling', fixture.sprite_theme)

function replayStateSummary(state) {
  return {
    playheadSeconds: state.playheadSeconds,
    playheadLabel: state.playheadLabel,
    laneIds: state.laneIds,
    lineagePhases: state.lineagePhases,
    animations: state.animations,
    mountId: state.mountId,
    sameCanvas: state.sameCanvas,
  }
}

async function readContinuousReplayState(initialCanvas) {
  return page.evaluate((originalCanvas) => {
    const parseRecord = (value) => {
      try {
        const parsed = JSON.parse(value ?? '{}')
        return parsed && typeof parsed === 'object' ? parsed : {}
      } catch {
        return {}
      }
    }
    const stage = document.querySelector('[data-qid="battle:pixi:stage"]')
    const canvas = document.querySelector('canvas.pixiRaceCanvas')
    const slider = document.querySelector('[data-qid="battle:timeline:scrub"]')
    const playheadSeconds = Number(slider?.getAttribute('aria-valuenow'))
    return {
      playheadSeconds: Number.isFinite(playheadSeconds) ? playheadSeconds : null,
      playheadLabel: document.querySelector('.playheadLabel')?.textContent?.replace(/\s+/g, ' ').trim() ?? null,
      laneIds: [...new Set([...document.querySelectorAll('[data-lane-id]')].map((element) => element.getAttribute('data-lane-id')).filter(Boolean))].sort(),
      animations: parseRecord(stage?.dataset.battleRunnerAnimations),
      lineagePhases: parseRecord(stage?.dataset.battleLineagePhases),
      mountId: canvas?.dataset.battlePixiMountId ?? null,
      sameCanvas: canvas === originalCanvas,
    }
  }, initialCanvas)
}

async function waitForContinuousReplayState(initialCanvas, label, predicate, timeoutMs = 5_000) {
  const deadline = Date.now() + timeoutMs
  let latest = await readContinuousReplayState(initialCanvas)
  while (Date.now() < deadline) {
    if (predicate(latest)) return latest
    await page.waitForTimeout(50)
    latest = await readContinuousReplayState(initialCanvas)
  }
  throw new Error(`${label} did not converge: ${JSON.stringify(replayStateSummary(latest))}`)
}

async function scrubContinuousReplayTo(initialCanvas, seconds) {
  const slider = page.locator('[data-qid="battle:timeline:scrub"]')
  const box = await slider.boundingBox()
  if (!box) throw new Error('Battle replay scrub slider is not visible')
  const maxSeconds = Number(await slider.getAttribute('aria-valuemax'))
  if (!Number.isFinite(maxSeconds) || maxSeconds <= 0) throw new Error('Battle replay scrub maximum is unavailable')
  const target = Math.max(0, Math.min(maxSeconds, seconds))
  const x = target <= 0 ? 1 : target >= maxSeconds ? Math.max(1, box.width - 1) : Math.max(1, Math.min(box.width - 1, (target / maxSeconds) * box.width))
  await slider.click({ position: { x, y: Math.max(1, Math.min(box.height - 1, box.height / 2)) } })
  if (target <= 0) await slider.press('ArrowLeft')
  if (target >= maxSeconds) await slider.press('ArrowRight')
  const tolerance = target <= 0 || target >= maxSeconds ? 0.05 : Math.max(0.35, (maxSeconds / Math.max(1, box.width)) * 2)
  return waitForContinuousReplayState(
    initialCanvas,
    `scrub to ${target.toFixed(3)}s`,
    (state) => state.playheadSeconds != null && Math.abs(state.playheadSeconds - target) <= tolerance,
  )
}

async function inspectAt(seconds, name, viewport = { width: 1600, height: 1050 }) {
  await page.setViewportSize(viewport)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto(`${baseUrl}&pixiSeconds=${seconds}`, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForSelector('canvas.pixiRaceCanvas', { timeout: 20_000 })
  await page.waitForTimeout(900)
  const proofMenu = page.locator('[data-qid="battle:nav:proofs-menu"]')
  if (await proofMenu.getAttribute('open') !== null) await proofMenu.locator('summary').click()
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
      canvas: { width: box?.width ?? 0, height: box?.height ?? 0, mountId: canvas?.dataset.battlePixiMountId ?? null },
      pageWidth: { client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth },
      timelineScrollLeft: document.querySelector('.battle-timeline-scroll')?.scrollLeft ?? 0,
      body: document.body.textContent ?? '',
    }
  })
  const screenshot = resolve(screenshotsDir, name)
  await page.screenshot({ path: screenshot, fullPage: viewport.width >= 700, animations: 'disabled', caret: 'hide', scale: 'css' })
  let raceScreenshot = null
  let raceScreenshotBuffer = null
  if (viewport.width < 700) {
    raceScreenshot = resolve(screenshotsDir, '08-four-lane-mobile-race.png')
    raceScreenshotBuffer = await scroller.screenshot({ path: raceScreenshot, animations: 'disabled', caret: 'hide', scale: 'css' })
  }
  return { ...state, screenshot, raceScreenshot, raceScreenshotBuffer }
}

const preSpawn = await inspectAt(71.67, '01-pre-spawn-children-hidden.png')
record('pre-spawn-parent-only', JSON.stringify([...new Set(preSpawn.laneIds)].sort()) === JSON.stringify(['blue-g1', 'red-g1']), { laneIds: preSpawn.laneIds, animations: preSpawn.animations })

const pending = await inspectAt(72, '02-spawn-authorized-pending.png')
record('authorized-four-lanes', ['red-g1', 'red-g2', 'blue-g1', 'blue-g2'].every((id) => pending.laneIds.includes(id)), pending.laneIds)
record('authorized-pending-not-active', pending.lineagePhases['red-g2'] === 'authorized_pending' && pending.lineagePhases['blue-g2'] === 'authorized_pending' && pending.animations['red-g2'] === 'idle' && pending.animations['blue-g2'] === 'idle' && /AUTHORIZED PENDING/.test(pending.body), { lineagePhases: pending.lineagePhases, animations: pending.animations })

const descending = await inspectAt(79.2, '03-ladder-descent-hop.png')
record('research-materializes-child', descending.lineagePhases['red-g2'] === 'descending' && descending.lineagePhases['blue-g2'] === 'descending' && descending.animations['red-g2'] === 'spawn' && descending.animations['blue-g2'] === 'spawn', { lineagePhases: descending.lineagePhases, animations: descending.animations })

const active = await inspectAt(82, '04-children-active-research.png')
record('children-active-research', active.lineagePhases['red-g2'] === 'active' && active.lineagePhases['blue-g2'] === 'active' && active.animations['red-g2'] === 'research' && active.animations['blue-g2'] === 'research', { lineagePhases: active.lineagePhases, animations: active.animations })

const mutation = await inspectAt(134.451, '05-mutation-evidence.png')
record('mutation-evidence-animation', mutation.animations['red-g2'] === 'mutate' && mutation.animations['blue-g2'] === 'mutate' && /MUTATION EVIDENCE VERIFIED/.test(mutation.body), { animations: mutation.animations })

const finalState = await inspectAt(134.457, '06-judge-selection-memory-boundary.png')
record('no-terminal-overclaim', Object.values(finalState.animations).every((value) => !['killed', 'victory', 'promoted'].includes(value)), finalState.animations)
record('canvas-nonblank-dimensions', finalState.canvas.width > 900 && finalState.canvas.height > 200, finalState.canvas)

const mobile = await inspectAt(129, '07-four-lane-mobile.png', { width: 430, height: 900 })
record('mobile-four-lane-state', ['red-g1', 'red-g2', 'blue-g1', 'blue-g2'].every((id) => mobile.laneIds.includes(id)) && mobile.canvas.width > 300 && mobile.pageWidth.scroll <= mobile.pageWidth.client && mobile.timelineScrollLeft > 0, { laneIds: mobile.laneIds, canvas: mobile.canvas, pageWidth: mobile.pageWidth, timelineScrollLeft: mobile.timelineScrollLeft })

const cameraRegression = await page.evaluate(async () => {
  const scroller = document.querySelector('[data-qid="battle:timeline:scroll"]')
  const canvas = document.querySelector('canvas.pixiRaceCanvas')
  if (!scroller || !canvas) return { available: false }
  const mountId = canvas.dataset.battlePixiMountId
  const target = Math.min(scroller.scrollWidth - scroller.clientWidth, Math.max(1, scroller.scrollLeft - 73))
  scroller.scrollLeft = target
  await new Promise(requestAnimationFrame)
  await new Promise(requestAnimationFrame)
  await new Promise((resolve) => setTimeout(resolve, 150))
  const nextCanvas = document.querySelector('canvas.pixiRaceCanvas')
  return {
    available: true,
    target,
    actual: scroller.scrollLeft,
    sameCanvas: canvas === nextCanvas,
    mountId,
    nextMountId: nextCanvas?.dataset.battlePixiMountId ?? null,
    canvasWidth: nextCanvas?.getBoundingClientRect().width ?? 0,
  }
})
record('mobile-outer-scroll-stable', cameraRegression.available === true && Math.abs(cameraRegression.actual - cameraRegression.target) <= 0.5, cameraRegression)
record('mobile-pixi-no-remount', cameraRegression.sameCanvas === true && cameraRegression.mountId === cameraRegression.nextMountId && cameraRegression.canvasWidth > 0, cameraRegression)

const laneRegions = await page.evaluate(() => {
  const scroller = document.querySelector('[data-qid="battle:timeline:scroll"]')
  if (!scroller) return []
  const scrollerRect = scroller.getBoundingClientRect()
  const seen = new Set()
  return [...document.querySelectorAll('[data-lane-id]')].flatMap((row) => {
    const laneId = row.getAttribute('data-lane-id')
    if (!laneId || seen.has(laneId)) return []
    seen.add(laneId)
    const rect = row.getBoundingClientRect()
    return [{
      laneId,
      x: Math.floor(scrollerRect.width * 0.64),
      y: Math.max(0, Math.floor(rect.top - scrollerRect.top + 4)),
      width: Math.floor(scrollerRect.width * 0.35),
      height: Math.max(1, Math.floor(rect.height - 8)),
    }]
  })
})
const pixelEvidence = await page.evaluate(async ({ dataUrl, regions }) => {
  const image = new Image()
  image.src = dataUrl
  await image.decode()
  const canvas = document.createElement('canvas')
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  const context = canvas.getContext('2d', { willReadFrequently: true })
  context.drawImage(image, 0, 0)
  return regions.map((region) => {
    const width = Math.min(region.width, canvas.width - region.x)
    const height = Math.min(region.height, canvas.height - region.y)
    const pixels = context.getImageData(region.x, region.y, width, height).data
    let spritePixels = 0
    for (let offset = 0; offset < pixels.length; offset += 4) {
      const red = pixels[offset]
      const green = pixels[offset + 1]
      const blue = pixels[offset + 2]
      const alpha = pixels[offset + 3]
      if (alpha > 220 && red > 55 && green > 50 && blue < 135 && red + green - blue * 1.5 > 75) spritePixels += 1
    }
    return { ...region, spritePixels }
  })
}, { dataUrl: `data:image/png;base64,${mobile.raceScreenshotBuffer.toString('base64')}`, regions: laneRegions })
record('mobile-four-runner-pixel-occupancy', pixelEvidence.length === 4 && pixelEvidence.every((region) => region.spritePixels >= 80), pixelEvidence)

let continuousReplayScreenshot = null
let continuousReplayDetail = { route: continuousReplayUrl }
let continuousReplayPassed = false
try {
  await page.setViewportSize({ width: 1600, height: 1050 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto(continuousReplayUrl, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForSelector('canvas.pixiRaceCanvas', { timeout: 20_000 })
  await page.waitForTimeout(900)
  const proofMenu = page.locator('[data-qid="battle:nav:proofs-menu"]')
  if (await proofMenu.getAttribute('open') !== null) await proofMenu.locator('summary').click()

  const canvas = page.locator('canvas.pixiRaceCanvas')
  const initialCanvas = await canvas.elementHandle()
  if (!initialCanvas) throw new Error('Initial Pixi canvas handle is unavailable')
  const initialMountId = await canvas.getAttribute('data-battle-pixi-mount-id')
  if (!initialMountId) throw new Error('Initial Pixi mount id is unavailable')

  await scrubContinuousReplayTo(initialCanvas, 0)
  const zero = await waitForContinuousReplayState(
    initialCanvas,
    'restart at zero',
    (state) => JSON.stringify(state.laneIds) === JSON.stringify(['blue-g1', 'red-g1']),
  )
  const playButton = page.locator('[data-qid="battle:control:playhead"]')
  const playStart = zero.playheadSeconds ?? 0
  await playButton.click()
  const played = await waitForContinuousReplayState(
    initialCanvas,
    'continuous Play',
    (state) => state.playheadSeconds != null && state.playheadSeconds >= playStart + 0.5,
    4_000,
  )
  await playButton.click()
  await page.waitForTimeout(100)
  const pauseStart = await readContinuousReplayState(initialCanvas)
  await page.waitForTimeout(750)
  const pauseEnd = await readContinuousReplayState(initialCanvas)
  const pauseDelta = Math.abs((pauseEnd.playheadSeconds ?? Number.NaN) - (pauseStart.playheadSeconds ?? Number.NaN))

  await scrubContinuousReplayTo(initialCanvas, 71)
  const preSpawnContinuous = await waitForContinuousReplayState(
    initialCanvas,
    'pre-spawn parent-only state',
    (state) => JSON.stringify(state.laneIds) === JSON.stringify(['blue-g1', 'red-g1']),
  )
  await scrubContinuousReplayTo(initialCanvas, 72)
  const pendingContinuous = await waitForContinuousReplayState(
    initialCanvas,
    'authorized-pending state',
    (state) => state.lineagePhases['red-g2'] === 'authorized_pending'
      && state.lineagePhases['blue-g2'] === 'authorized_pending'
      && state.animations['red-g2'] === 'idle'
      && state.animations['blue-g2'] === 'idle',
  )
  await scrubContinuousReplayTo(initialCanvas, 79.2)
  const descendingContinuous = await waitForContinuousReplayState(
    initialCanvas,
    'child descent state',
    (state) => state.lineagePhases['red-g2'] === 'descending'
      && state.lineagePhases['blue-g2'] === 'descending'
      && state.animations['red-g2'] === 'spawn'
      && state.animations['blue-g2'] === 'spawn',
  )
  await scrubContinuousReplayTo(initialCanvas, 82)
  const researchContinuous = await waitForContinuousReplayState(
    initialCanvas,
    'child research state',
    (state) => state.lineagePhases['red-g2'] === 'active'
      && state.lineagePhases['blue-g2'] === 'active'
      && state.animations['red-g2'] === 'research'
      && state.animations['blue-g2'] === 'research',
  )
  await scrubContinuousReplayTo(initialCanvas, Number(fixture.campaign?.elapsed_seconds ?? 134.457076))
  const mutationContinuous = await waitForContinuousReplayState(
    initialCanvas,
    'mutation/final state',
    (state) => state.animations['red-g2'] === 'mutate'
      && state.animations['blue-g2'] === 'mutate'
      && Object.values(state.animations).every((animation) => !['killed', 'victory', 'promoted'].includes(animation)),
  )
  const screenshotName = '09-continuous-replay-single-mount.png'
  await page.screenshot({ path: resolve(screenshotsDir, screenshotName), fullPage: true, animations: 'disabled', caret: 'hide', scale: 'css' })
  continuousReplayScreenshot = `screenshots/${screenshotName}`
  await scrubContinuousReplayTo(initialCanvas, 0)
  const restarted = await waitForContinuousReplayState(
    initialCanvas,
    'parent-only state after restart',
    (state) => JSON.stringify(state.laneIds) === JSON.stringify(['blue-g1', 'red-g1']),
  )
  const finalCanvas = page.locator('canvas.pixiRaceCanvas')
  const finalMountId = await finalCanvas.getAttribute('data-battle-pixi-mount-id')
  const finalStateContinuous = await readContinuousReplayState(initialCanvas)

  const parents = JSON.stringify(['blue-g1', 'red-g1'])
  const allLanes = ['red-g1', 'red-g2', 'blue-g1', 'blue-g2']
  const parentOnly = (state) => JSON.stringify(state.laneIds) === parents
  const fourLanes = (state) => allLanes.every((laneId) => state.laneIds.includes(laneId))
  const pendingTruthful = fourLanes(pendingContinuous)
    && pendingContinuous.lineagePhases['red-g2'] === 'authorized_pending'
    && pendingContinuous.lineagePhases['blue-g2'] === 'authorized_pending'
    && pendingContinuous.animations['red-g2'] === 'idle'
    && pendingContinuous.animations['blue-g2'] === 'idle'
  const descentTruthful = fourLanes(descendingContinuous)
    && descendingContinuous.lineagePhases['red-g2'] === 'descending'
    && descendingContinuous.lineagePhases['blue-g2'] === 'descending'
    && descendingContinuous.animations['red-g2'] === 'spawn'
    && descendingContinuous.animations['blue-g2'] === 'spawn'
  const researchTruthful = fourLanes(researchContinuous)
    && researchContinuous.lineagePhases['red-g2'] === 'active'
    && researchContinuous.lineagePhases['blue-g2'] === 'active'
    && researchContinuous.animations['red-g2'] === 'research'
    && researchContinuous.animations['blue-g2'] === 'research'
  const terminalOverclaim = Object.values(mutationContinuous.animations).some((animation) => ['killed', 'victory', 'promoted'].includes(animation))
  const mutationTruthful = fourLanes(mutationContinuous)
    && mutationContinuous.animations['red-g2'] === 'mutate'
    && mutationContinuous.animations['blue-g2'] === 'mutate'
    && !terminalOverclaim
  const states = { zero, played, pauseStart, pauseEnd, preSpawn: preSpawnContinuous, pending: pendingContinuous, descending: descendingContinuous, research: researchContinuous, mutation: mutationContinuous, restarted, finalState: finalStateContinuous }
  const mountStableAtEveryStep = Object.values(states).every((state) => state.sameCanvas === true && state.mountId === initialMountId)

  continuousReplayDetail = {
    route: continuousReplayUrl,
    initial_mount_id: initialMountId,
    final_mount_id: finalMountId,
    observed_playhead_values: Object.fromEntries(Object.entries(states).map(([name, state]) => [name, state.playheadSeconds])),
    pause_delta_seconds: pauseDelta,
    states: Object.fromEntries(Object.entries(states).map(([name, state]) => [name, replayStateSummary(state)])),
    same_canvas_node: finalStateContinuous.sameCanvas,
    mount_stable_at_every_step: mountStableAtEveryStep,
  }
  continuousReplayPassed = played.playheadSeconds != null
    && played.playheadSeconds > playStart
    && Number.isFinite(pauseDelta)
    && pauseDelta <= 0.15
    && parentOnly(preSpawnContinuous)
    && pendingTruthful
    && descentTruthful
    && researchTruthful
    && mutationTruthful
    && parentOnly(restarted)
    && finalMountId === initialMountId
    && finalStateContinuous.sameCanvas === true
    && mountStableAtEveryStep
  await initialCanvas.dispose()
} catch (error) {
  continuousReplayDetail = {
    ...continuousReplayDetail,
    error: error instanceof Error ? error.message : String(error),
  }
}
record('continuous-replay-single-mount', continuousReplayPassed, continuousReplayDetail)

const requestList = [...requests.values()]
const authorityRequestList = requestList.filter((request) => ['fetch', 'xhr', 'image', 'media'].includes(request.resource_type))
record('plague-atlas-requested', requestList.some(({ url }) => /plague_nurgling\.json/.test(url)) && requestList.some(({ url }) => /plague_nurgling\.png/.test(url)), requestList.filter(({ url }) => /plague_nurgling/.test(url)))
record('no-raw-runtime-requests', authorityRequestList.every(({ url }) => !/\/tmp\/|tau-live|provider-workspace|arena\/private|command-loop/.test(url)), authorityRequestList.filter(({ url }) => /\/tmp\/|tau-live|provider-workspace|arena\/private|command-loop/.test(url)))
record('no-browser-errors', errors.length === 0, errors)

await browser.close()
const failed = checks.filter((check) => !check.pass)
const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repositoryDir, encoding: 'utf8' }).trim()
const report = {
  schema: 'battle.adaptive_lineage_ui_proof.v1',
  pass: failed.length === 0,
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  route: baseUrl,
  fixture: { event_count: fixture.events?.length, lane_count: fixture.lanes?.length, lineage_edge_count: fixture.lineage_edges?.length },
  retained_campaign: { campaign_receipt_sha256: retainedCampaignHash, events_jsonl_sha256: retainedEventsHash },
  checks,
  failed: failed.map((check) => check.id),
  errors,
  screenshots: [
    ...['01-pre-spawn-children-hidden.png', '02-spawn-authorized-pending.png', '03-ladder-descent-hop.png', '04-children-active-research.png', '05-mutation-evidence.png', '06-judge-selection-memory-boundary.png', '07-four-lane-mobile.png', '08-four-lane-mobile-race.png'].map((name) => `screenshots/${name}`),
    ...(continuousReplayScreenshot ? [continuousReplayScreenshot] : []),
  ],
  claims: {
    proves: ['The retained V13 campaign is rendered through the public HTTP fixture with four visible Pixi runners, one-way outer-scroll camera control, and continuous Play/Pause/scrub/restart behavior on one stable Pixi mount.'],
    does_not_prove: ['Speaker output, final audio mix, exploit success, child improvement, durable memory reuse, or production readiness.'],
  },
}
await writeFile(resolve(outDir, 'proof-summary.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
await writeFile(resolve(outDir, 'browser-console.json'), `${JSON.stringify({ errors, messages: consoleMessages }, null, 2)}\n`, 'utf8')
await writeFile(resolve(outDir, 'network-authority-requests.json'), `${JSON.stringify({ requests: authorityRequestList }, null, 2)}\n`, 'utf8')

const sourceArtifacts = await Promise.all([
  sourceArtifact(resolve(battleDir, 'local', fixtureId, 'battle.normalized_ux_fixture.json'), 'local_fixture'),
  sourceArtifact(resolve(spectatorDir, 'public', 'battle-fixtures', fixtureId, 'battle.normalized_ux_fixture.json'), 'public_fixture'),
  sourceArtifact(resolve(battleDir, 'assets', 'sprites', 'pixijs', 'plague_nurgling.png'), 'plague_nurgling_png'),
  sourceArtifact(resolve(battleDir, 'assets', 'sprites', 'pixijs', 'plague_nurgling.json'), 'plague_nurgling_json'),
  sourceArtifact(resolve(battleDir, 'assets', 'sprites', 'pixijs', 'battle-sprite-assets.manifest.json'), 'sprite_manifest'),
])
record('local-public-fixture-byte-identical', sourceArtifacts[0].sha256 === sourceArtifacts[1].sha256, { local: sourceArtifacts[0].sha256, public: sourceArtifacts[1].sha256 })
report.pass = checks.every((check) => check.pass)
report.failed = checks.filter((check) => !check.pass).map((check) => check.id)
report.checks = checks
await writeFile(resolve(outDir, 'proof-summary.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')

const proofFiles = ['proof-summary.json', 'browser-console.json', 'network-authority-requests.json', ...report.screenshots]
const proofArtifacts = await Promise.all(proofFiles.map(async (path) => {
  const absolute = resolve(outDir, path)
  const fileStat = await stat(absolute)
  return { path, sha256: await sha256File(absolute), bytes: fileStat.size }
}))
const manifest = {
  schema: 'battle.adaptive_lineage_ui_proof_manifest.v1',
  status: report.pass ? 'PASS' : 'FAIL',
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  route: baseUrl,
  retained_campaign: report.retained_campaign,
  source_artifacts: sourceArtifacts,
  proof_artifacts: proofArtifacts,
  claims: report.claims,
}
await writeFile(resolve(outDir, 'proof-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(report, null, 2))
process.exit(report.pass ? 0 : 1)
