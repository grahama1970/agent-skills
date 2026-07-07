#!/usr/bin/env node
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3012'
const baseUrl = process.env.BATTLE_RECEIPT_URL ?? `${host}/#battle/receipt?engine=pixi`
const outDir = resolve(process.env.BATTLE_RECEIPT_CAPTURE_DIR ?? '/tmp/battle-receipt-pixi-sanity')
const spawnAt = Number(process.env.BATTLE_RECEIPT_SPAWN_SECONDS ?? '116.973449')

async function main() {
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
    lanes: [...document.querySelectorAll('[data-qid^="battle:lane:"]')].map((el) => el.getAttribute('data-qid')),
    parent: !!document.querySelector('[data-qid="battle:lane:payload-857-receipt"]'),
    child: !!document.querySelector('[data-qid="battle:lane:payload-857-red-1"]'),
  }))

  await page.goto(`${baseUrl}${baseUrl.includes('?') ? '&' : '?'}pixiTest=1&pixiSeconds=${spawnAt - 5}`, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForTimeout(2500)
  const pre = await page.evaluate(() => ({
    child: !!document.querySelector('[data-qid="battle:lane:payload-857-red-1"]'),
    parent: !!document.querySelector('[data-qid="battle:lane:payload-857-receipt"]'),
  }))
  await page.screenshot({ path: resolve(outDir, 'before-spawn.png') })

  await page.goto(`${baseUrl.split('?')[0]}?engine=pixi&pixiTest=1&pixiSeconds=${spawnAt + 5}`, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForTimeout(2500)
  const post = await page.evaluate(() => ({
    child: !!document.querySelector('[data-qid="battle:lane:payload-857-red-1"]'),
    parent: !!document.querySelector('[data-qid="battle:lane:payload-857-receipt"]'),
  }))
  await page.screenshot({ path: resolve(outDir, 'after-spawn.png') })

  // scrub test on receipt route
  await page.goto('http://127.0.0.1:3012/#battle/receipt?engine=pixi', { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForTimeout(2000)
  const labelBefore = await page.textContent('.playheadLabel')
  const track = page.locator('.playheadTrack').first()
  const box = await track.boundingBox()
  if (box) await page.mouse.click(box.x + box.width * 0.2, box.y + box.height / 2)
  await page.waitForTimeout(400)
  const labelAfter = await page.textContent('.playheadLabel')

  await browser.close()

  if (errors.length) {
    console.error(errors.slice(0, 5).join('\n'))
    process.exit(1)
  }
  if (!pre.parent || pre.child) {
    console.error('child visible before spawn', pre)
    process.exit(1)
  }
  if (!post.parent || !post.child) {
    console.error('child missing after spawn', post)
    process.exit(1)
  }
  if (labelBefore === labelAfter) {
    console.error('scrub did not move playhead', { labelBefore, labelAfter })
    process.exit(1)
  }

  console.log('PASS battle-receipt-pixi-sanity')
  console.log(JSON.stringify({ beforeSpawn, pre, post, scrub: { labelBefore, labelAfter }, screenshots: outDir }, null, 2))
}

main().catch((error) => { console.error(error); process.exit(1) })
