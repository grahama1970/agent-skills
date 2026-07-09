#!/usr/bin/env node
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const baseUrl = process.env.BATTLE_RECEIPT_URL ?? `${host}/#battle/receipt?engine=pixi`
const outDir = resolve(process.env.BATTLE_RECEIPT_PROOF_DIR ?? '/tmp/battle-receipt-replay-6-proof')

const checks = []

function record(id, pass, detail) {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

async function main() {
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })

  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForTimeout(2000)

  const req1 = await page.evaluate(() => ({
    parent: !!document.querySelector('[data-qid="battle:lane:payload-857-receipt"]'),
    laneQids: [...document.querySelectorAll('[data-qid^="battle:lane:"]')].map((el) => el.getAttribute('data-qid')).filter((q) => !q.includes('collapse')),
    mockup857: !!document.querySelector('[data-qid="battle:lane:payload-857"]'),
  }))
  record('1-receipt-lanes', req1.parent && !req1.mockup857 && req1.laneQids.includes('battle:lane:payload-857-receipt'), JSON.stringify(req1))

  const fixtureFetch = await page.evaluate(async () => {
    const r = await fetch('/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json')
    if (!r.ok) return { ok: false, status: r.status }
    const j = await r.json()
    const spawn = (j.lineage?.spawns ?? []).find((item) => item.child_lane_id === 'payload-857-red-1')
    return {
      ok: true,
      laneIds: (j.lanes ?? []).map((l) => l.id),
      lineage: j.lineage?.spawn_count,
      spawnAt: spawn?.visible_from_elapsed_seconds ?? spawn?.spawn_elapsed_seconds,
      allottedSeconds: j.battle_clock?.allotted_seconds ?? j.clock?.allotted_seconds ?? 1200,
    }
  })
  record(
    '2-fixture-fetch',
    fixtureFetch.ok && fixtureFetch.laneIds?.includes('payload-857-receipt') && Number.isFinite(fixtureFetch.spawnAt),
    JSON.stringify(fixtureFetch),
  )

  const pixiInput = await page.evaluate(() => ({
    engine: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine'),
    viewportSeconds: document.querySelector('[data-battle-viewport-seconds]')?.getAttribute('data-battle-viewport-seconds'),
    canvas: document.querySelectorAll('canvas').length,
  }))
  record('3-pixi-input', pixiInput.engine === 'animated-sprites' && Number(pixiInput.viewportSeconds) >= 0 && pixiInput.canvas === 1, JSON.stringify(pixiInput))

  const beforeScrub = await page.evaluate(() => ({
    label: document.querySelector('.playheadLabel')?.textContent,
    viewport: document.querySelector('[data-battle-viewport-seconds]')?.getAttribute('data-battle-viewport-seconds'),
  }))
  const track = page.locator('.playheadTrack').first()
  const box = await track.boundingBox()
  if (box) await page.mouse.click(box.x + box.width * 0.2, box.y + box.height / 2)
  await page.waitForTimeout(600)
  const afterScrub = await page.evaluate(() => ({
    label: document.querySelector('.playheadLabel')?.textContent,
    viewport: document.querySelector('[data-battle-viewport-seconds]')?.getAttribute('data-battle-viewport-seconds'),
  }))
  const scrubChanged = beforeScrub.label !== afterScrub.label && beforeScrub.viewport !== afterScrub.viewport
  record('4-scrub-sync', scrubChanged, JSON.stringify({ beforeScrub, afterScrub }))

  const allotted = Number.isFinite(fixtureFetch.allottedSeconds) ? fixtureFetch.allottedSeconds : 1200
  const spawnAt = Number(fixtureFetch.spawnAt)
  async function scrubPlayheadToSeconds(targetSeconds) {
    const track = page.locator('.playheadTrack').first()
    const box = await track.boundingBox()
    if (!box) throw new Error('playhead track missing')
    const pct = Math.max(0, Math.min(1, targetSeconds / allotted))
    await page.mouse.click(box.x + box.width * pct, box.y + box.height / 2)
    await page.waitForTimeout(600)
  }

  await scrubPlayheadToSeconds(spawnAt - 5)
  const pre = await page.evaluate(() => ({
    child: !!document.querySelector('[data-qid="battle:lane:payload-857-red-1"]'),
    parent: !!document.querySelector('[data-qid="battle:lane:payload-857-receipt"]'),
    viewport: document.querySelector('[data-battle-viewport-seconds]')?.getAttribute('data-battle-viewport-seconds'),
  }))
  record('5-child-before-spawn-hidden', pre.parent && !pre.child, JSON.stringify(pre))

  await scrubPlayheadToSeconds(spawnAt + 5)
  const post = await page.evaluate(() => ({
    child: !!document.querySelector('[data-qid="battle:lane:payload-857-red-1"]'),
    parent: !!document.querySelector('[data-qid="battle:lane:payload-857-receipt"]'),
    viewport: document.querySelector('[data-battle-viewport-seconds]')?.getAttribute('data-battle-viewport-seconds'),
  }))
  record('6-child-after-spawn-visible', post.parent && post.child, JSON.stringify(post))

  const lifecycle = await page.evaluate(() => {
    const panel = document.querySelector('[data-qid="battle:agent-pane:lifecycle-evidence"]')
    const text = panel?.textContent ?? ''
    return {
      panel: Boolean(panel),
      text,
      hasKnowledge: text.includes('knowledge_packet'),
      hasPromotion: text.includes('memory_promotion'),
      hasPacketCapture: text.includes('packet capture'),
      hasCalibration: text.includes('score_calibration'),
    }
  })
  record(
    '7-lifecycle-evidence',
    lifecycle.panel && lifecycle.hasKnowledge && lifecycle.hasPromotion && lifecycle.hasPacketCapture && lifecycle.hasCalibration,
    JSON.stringify(lifecycle),
  )

  await page.screenshot({ path: resolve(outDir, 'receipt-replay-proof.png') })
  await browser.close()

  const pass = checks.every((c) => c.pass) && errors.length === 0
  const report = { pass, checks, errors, mocked: false, live: true, screenshots: outDir }
  console.log(JSON.stringify(report, null, 2))
  process.exit(pass ? 0 : 1)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
