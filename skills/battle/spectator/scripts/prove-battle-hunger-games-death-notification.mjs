#!/usr/bin/env node
/**
 * Live UX proof for Hunger Games death notification in the LIVE EVENTS panel.
 * Does not require a kill receipt — uses isolation harness + hgDeathDemo hook.
 */
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3002'
const isolationUrl = `${host}/#battle/isolation`
const receiptDemoUrl = `${host}/#battle/receipt?engine=pixi&hgDeathDemo=1`
const outDir = resolve(process.env.BATTLE_HG_DEATH_PROOF_DIR ?? '/tmp/battle-hg-death-notification-proof')

const checks = []

function record(id, pass, detail) {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

async function assertDeathCard(page, contextLabel) {
  const card = page.locator('[data-qid="battle:death-announcement"]').first()
  await card.waitFor({ state: 'visible', timeout: 15_000 })

  const snapshot = await page.evaluate(() => {
    const root = document.querySelector('[data-qid="battle:death-announcement"]')
    if (!root) return { ok: false, reason: 'card-missing' }
    const inLiveEvents = Boolean(root.closest('.battle-live-events'))
    const name = root.querySelector('.battle-hg-death-name')?.textContent?.trim() ?? ''
    const infoLabel = root.querySelector('.battle-hg-death-info-label')?.textContent?.trim() ?? ''
    const infoBody = root.querySelector('.battle-hg-death-body')?.textContent?.trim() ?? root.querySelector('.battle-hg-death-info-body')?.textContent?.trim() ?? ''
    const portraitSrc = root.querySelector('.battle-hg-death-portrait')?.getAttribute('src') ?? ''
    return {
      ok: true,
      inLiveEvents,
      name,
      infoLabel,
      infoBody,
      portraitSrc,
      hasNameplate: Boolean(root.querySelector('.battle-hg-death-nameplate')),
      hasDashedInfo: Boolean(root.querySelector('.battle-hg-death-info-panel')),
    }
  })

  record(`${contextLabel}-card-visible`, snapshot.ok, JSON.stringify(snapshot))
  record(`${contextLabel}-in-live-events`, snapshot.inLiveEvents, JSON.stringify({ inLiveEvents: snapshot.inLiveEvents }))
  record(
    `${contextLabel}-hg-layout`,
    snapshot.infoLabel === 'Virus Information' &&
      snapshot.hasNameplate &&
      snapshot.hasDashedInfo &&
      snapshot.name.length > 0 &&
      snapshot.infoBody.includes('Payload') &&
      snapshot.portraitSrc.includes('/battle-sprites/pixijs/'),
    JSON.stringify(snapshot),
  )

  return snapshot
}

async function main() {
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await page.goto(isolationUrl, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-testid="isolation-hunger-games-death-notification"]', { timeout: 15_000 })
  await assertDeathCard(page, 'isolation')
  await page.screenshot({ path: resolve(outDir, 'isolation-hg-death-notification.png'), fullPage: true })

  await page.goto(receiptDemoUrl, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('.battle-live-events', { timeout: 15_000 })
  await assertDeathCard(page, 'receipt-demo')
  await page.screenshot({ path: resolve(outDir, 'receipt-hg-death-notification.png'), fullPage: true })

  await browser.close()

  if (errors.length) {
    console.error('page errors:', errors.slice(0, 5).join('\n'))
    record('page-errors', false, errors.slice(0, 3).join(' | '))
  }

  const failed = checks.filter((check) => !check.pass)
  console.log(JSON.stringify({ checks, outDir, failed: failed.length }, null, 2))
  if (failed.length) process.exit(1)
  console.log('BATTLE_PROVE_HG_DEATH_NOTIFICATION_PASS')
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
