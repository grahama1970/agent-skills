#!/usr/bin/env node
/**
 * Live proof: replay playhead crossing a proven kill fires HG death card in LIVE EVENTS.
 */
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3002'
const baseUrl = `${host}/#battle/receipt?engine=pixi&fixture=battle-004-kill-shot`
const outDir = resolve(process.env.BATTLE_HG_KILL_CUE_PROOF_DIR ?? '/tmp/battle-hg-kill-cue-replay-proof')
const TRAVEL = 0.55

const checks = []
function record(id, pass, detail) {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

async function readPlayheadSeconds(page) {
  const label = await page.textContent('.playheadLabel')
  const match = label?.match(/(\d+):(\d+)/)
  if (!match) return 0
  return Number(match[1]) * 60 + Number(match[2])
}

async function scrubPlayheadToSeconds(page, targetSeconds) {
  const track = page.locator('.playheadTrack').first()
  await track.focus()
  let current = await readPlayheadSeconds(page)
  const guard = 300
  let steps = 0
  while (current + 0.5 < targetSeconds && steps < guard) {
    await page.keyboard.press('ArrowRight')
    await page.waitForTimeout(60)
    current = await readPlayheadSeconds(page)
    steps += 1
  }
  while (current - 0.5 > targetSeconds && steps < guard) {
    await page.keyboard.press('ArrowLeft')
    await page.waitForTimeout(60)
    current = await readPlayheadSeconds(page)
    steps += 1
  }
  await page.waitForTimeout(400)
}

async function main() {
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })

  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-qid="battle:lane:payload-857-red-1"]', { timeout: 20_000 })

  const fixture = await page.evaluate(async () => {
    const r = await fetch('/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json')
    if (!r.ok) return { ok: false, status: r.status }
    const j = await r.json()
    const lane = (j.lanes ?? []).find((item) => item.id === 'payload-857-red-1')
    const blast = (lane?.events ?? []).find((event) => event.kind === 'blue_blast')
    const killed = (lane?.events ?? []).find((event) => event.kind === 'killed')
    return {
      ok: true,
      allotted: j.battle_clock?.allotted_seconds ?? j.clock?.allotted_seconds ?? 1200,
      blastAt: blast?.elapsed_seconds,
      killedAt: killed?.elapsed_seconds,
      killedKind: killed?.kind,
    }
  })
  record('fixture-kill-lane', fixture.ok && fixture.killedKind === 'killed', JSON.stringify(fixture))

  const blastAt = Number(fixture.blastAt)
  const impactAt = blastAt + TRAVEL
  const allotted = Number(fixture.allotted)

  await scrubPlayheadToSeconds(page, blastAt - 2)
  const before = await page.evaluate(() => ({
    card: !!document.querySelector('[data-qid="battle:death-announcement"]'),
    viewport: document.querySelector('[data-battle-viewport-seconds]')?.getAttribute('data-battle-viewport-seconds'),
  }))
  record('card-hidden-before-kill-crossing', !before.card, JSON.stringify(before))

  await scrubPlayheadToSeconds(page, impactAt + 0.3)
  await page.waitForSelector('[data-qid="battle:death-announcement"]', { timeout: 10_000 })

  const after = await page.evaluate(() => {
    const card = document.querySelector('[data-qid="battle:death-announcement"]')
    const ticker = [...document.querySelectorAll('.battle-live-event-row b')].map((el) => el.textContent?.trim() ?? '')
    return {
      card: !!card,
      inLiveEvents: Boolean(card?.closest('.battle-live-events')),
      name: card?.querySelector('.battle-hg-death-name')?.textContent?.trim() ?? '',
      info: card?.querySelector('.battle-hg-death-info-body')?.textContent?.trim() ?? '',
      tickerHighlights: ticker,
      viewport: document.querySelector('[data-battle-viewport-seconds]')?.getAttribute('data-battle-viewport-seconds'),
    }
  })
  record('card-visible-after-kill-crossing', after.card && after.inLiveEvents, JSON.stringify(after))
  record('hg-eliminated-copy', after.info.includes('Payload') && after.tickerHighlights.some((t) => t.includes('ELIMINATED')), JSON.stringify(after))
  record('no-stale-survival-highlight', !after.tickerHighlights.some((t) => /RED-1/i.test(t) && t.includes('SURVIVES')), JSON.stringify({ tickerHighlights: after.tickerHighlights }))

  await page.screenshot({ path: resolve(outDir, 'kill-cue-replay-death-card.png'), fullPage: true })
  await browser.close()

  if (errors.length) record('page-errors', false, errors.slice(0, 3).join(' | '))

  const failed = checks.filter((c) => !c.pass)
  console.log(JSON.stringify({ checks, outDir, failed: failed.length }, null, 2))
  if (failed.length) process.exit(1)
  console.log('BATTLE_PROVE_HG_KILL_CUE_REPLAY_PASS')
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
