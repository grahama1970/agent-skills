#!/usr/bin/env node
import { copyFile, mkdir, stat, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const fixtureId = process.env.BATTLE_RECEIPT_FIXTURE ?? 'battle-004-adaptive-lineage-v13'
const baseUrl = process.env.BATTLE_PIXI_GAMEPLAY_URL ?? `${host}/#battle/receipt?engine=pixi&fixture=${fixtureId}`
const outDir = resolve(process.env.BATTLE_PIXI_GAMEPLAY_OUT_DIR ?? '/tmp/battle-pixi-gameplay-video')
const screenshotsDir = resolve(outDir, 'screenshots')
const videoDir = resolve(outDir, 'video')
const receiptPath = resolve(outDir, 'pixi-gameplay-video-proof.json')
const finalVideoPath = resolve(videoDir, 'pixi-replay-gameplay.webm')

async function readReplayState(page, initialCanvas) {
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
    const source = document.querySelector('[data-qid="battle:race:source"]')
    const topPausePanel = document.querySelector('[data-qid="battle:human-interjection:panel"]')
    const pauseNa = document.querySelector('[data-qid="battle:human-interjection:receipt-replay-na"]')
    return {
      playheadSeconds: Number.isFinite(playheadSeconds) ? playheadSeconds : null,
      playheadLabel: document.querySelector('.playheadLabel')?.textContent?.replace(/\s+/g, ' ').trim() ?? null,
      laneIds: [...new Set([...document.querySelectorAll('[data-lane-id]')].map((element) => element.getAttribute('data-lane-id')).filter(Boolean))].sort(),
      animations: parseRecord(stage?.dataset.battleRunnerAnimations),
      lineagePhases: parseRecord(stage?.dataset.battleLineagePhases),
      source: {
        battle_id: source?.getAttribute('data-battle-id') ?? null,
        run_id: source?.getAttribute('data-run-id') ?? null,
        source_proof_id: source?.getAttribute('data-source-proof-id') ?? null,
        source_fixture_id: source?.getAttribute('data-source-fixture-id') ?? null,
        source_fixture_sha256: source?.getAttribute('data-source-fixture-sha256') ?? null,
      },
      pause_after_round: {
        top_panel_present: Boolean(topPausePanel),
        receipt_replay_non_applicable_present: Boolean(pauseNa),
      },
      canvasWidth: canvas?.width ?? null,
      canvasHeight: canvas?.height ?? null,
      sameCanvas: canvas === originalCanvas,
    }
  }, initialCanvas)
}

async function waitForState(page, initialCanvas, label, predicate, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs
  let latest = await readReplayState(page, initialCanvas)
  while (Date.now() < deadline) {
    if (predicate(latest)) return latest
    await page.waitForTimeout(75)
    latest = await readReplayState(page, initialCanvas)
  }
  throw new Error(`${label} did not converge: ${JSON.stringify(latest)}`)
}

async function scrubTo(page, initialCanvas, seconds) {
  const slider = page.locator('[data-qid="battle:timeline:scrub"]')
  const box = await slider.boundingBox()
  if (!box) throw new Error('Battle replay scrub slider is not visible')
  const maxSeconds = Number(await slider.getAttribute('aria-valuemax'))
  if (!Number.isFinite(maxSeconds) || maxSeconds <= 0) {
    throw new Error('Battle replay scrub maximum is unavailable')
  }
  const target = Math.max(0, Math.min(maxSeconds, seconds))
  const x = Math.max(1, Math.min(box.width - 1, (target / maxSeconds) * box.width))
  await page.evaluate(
    ({ clientX, clientY }) => {
      const slider = document.querySelector('[data-qid="battle:timeline:scrub"]')
      if (!slider) throw new Error('Battle replay scrub slider is not present')
      slider.dispatchEvent(new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        clientX,
        clientY,
      }))
    },
    { clientX: box.x + x, clientY: box.y + Math.max(1, Math.min(box.height - 1, box.height / 2)) },
  )
  const tolerance = Math.max(0.35, (maxSeconds / Math.max(1, box.width)) * 2)
  return waitForState(
    page,
    initialCanvas,
    `scrub to ${target.toFixed(3)}s`,
    (state) => state.playheadSeconds != null && Math.abs(state.playheadSeconds - target) <= tolerance,
  )
}

async function main() {
  await mkdir(outDir, { recursive: true })
  await mkdir(screenshotsDir, { recursive: true })
  await mkdir(videoDir, { recursive: true })

  const errors = []
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    recordVideo: { dir: videoDir, size: { width: 1280, height: 800 } },
  })
  const page = await context.newPage()
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })

  let receipt
  try {
    await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60_000 })
    await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
    await page.waitForSelector('canvas.pixiRaceCanvas', { timeout: 20_000 })
    await page.waitForTimeout(1500)
    const initialCanvas = await page.$('canvas.pixiRaceCanvas')
    if (!initialCanvas) throw new Error('Pixi canvas did not mount')

    const loaded = await waitForState(
      page,
      initialCanvas,
      'initial replay state',
      (state) => state.canvasWidth > 0 && state.canvasHeight > 0 && state.laneIds.length >= 2,
    )
    await page.screenshot({ path: resolve(screenshotsDir, 'loaded.png') })

    const zero = await scrubTo(page, initialCanvas, 0)
    const playButton = page.locator('[data-qid="battle:control:playhead"]')
    await playButton.click()
    const played = await waitForState(
      page,
      initialCanvas,
      'play advances playhead',
      (state) => state.playheadSeconds != null && state.playheadSeconds >= (zero.playheadSeconds ?? 0) + 0.5,
      5000,
    )
    await page.screenshot({ path: resolve(screenshotsDir, 'playing.png') })

    await playButton.click()
    await page.waitForTimeout(150)
    const pauseStart = await readReplayState(page, initialCanvas)
    await page.waitForTimeout(800)
    const pauseEnd = await readReplayState(page, initialCanvas)
    const pauseDelta = Math.abs((pauseEnd.playheadSeconds ?? Number.NaN) - (pauseStart.playheadSeconds ?? Number.NaN))

    const reset = await scrubTo(page, initialCanvas, 0)
    const jumped = await scrubTo(page, initialCanvas, 100)
    await page.screenshot({ path: resolve(screenshotsDir, 'scrubbed.png') })

    receipt = {
      schema: 'battle.pixi_gameplay_video_proof.v1',
      status: 'PASS',
      mocked: false,
      live: 'local_http_static_bundle_playwright_video_pixi_gameplay',
      fixture_id: fixtureId,
      base_url: baseUrl,
      loaded,
      played,
      pause_start: pauseStart,
      pause_end: pauseEnd,
      play_advanced: (played.playheadSeconds ?? 0) > (zero.playheadSeconds ?? 0),
      pause_stopped: Number.isFinite(pauseDelta) && pauseDelta < 0.2,
      scrub_reset_works: (reset.playheadSeconds ?? Number.NaN) <= 0.35,
      scrub_jump_works: (jumped.playheadSeconds ?? 0) >= 99,
      no_runtime_errors: errors.length === 0,
      source_identity_visible: loaded.source.battle_id === 'battle-004' && Boolean(loaded.source.run_id) && Boolean(loaded.source.source_fixture_sha256),
      pause_after_round_not_in_primary_replay: loaded.pause_after_round.top_panel_present === false && loaded.pause_after_round.receipt_replay_non_applicable_present === true,
      runtime_errors: errors,
      screenshots: {
        loaded: resolve(screenshotsDir, 'loaded.png'),
        playing: resolve(screenshotsDir, 'playing.png'),
        scrubbed: resolve(screenshotsDir, 'scrubbed.png'),
      },
      video_path: finalVideoPath,
      created_at: new Date().toISOString(),
    }
  } finally {
    await context.close()
    await browser.close()
  }

  const rawVideoPath = await page.video().path()
  await copyFile(rawVideoPath, finalVideoPath)
  const videoStat = await stat(finalVideoPath)
  receipt.video_bytes = videoStat.size
  if (!receipt.play_advanced || !receipt.pause_stopped || !receipt.scrub_reset_works || !receipt.scrub_jump_works || !receipt.source_identity_visible || !receipt.pause_after_round_not_in_primary_replay || errors.length) {
    receipt.status = 'FAIL'
  }
  await writeFile(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8')
  if (receipt.status !== 'PASS') {
    console.error(JSON.stringify(receipt, null, 2))
    process.exit(1)
  }
  console.log('PASS battle-pixi-gameplay-video')
  console.log(JSON.stringify({ receipt: receiptPath, video: finalVideoPath, videoBytes: videoStat.size }, null, 2))
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
