#!/usr/bin/env node
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { chromium } from 'playwright'

const baseUrl = process.env.BATTLE_PIXI_URL ?? 'http://127.0.0.1:3012/#battle?engine=pixi'
const outDir = resolve(process.env.BATTLE_PIXI_CAPTURE_DIR ?? '/tmp/battle-pixi-sanity')
const url = process.env.BATTLE_PIXI_TEST === '1'
  ? `${baseUrl}${baseUrl.includes('?') ? '&' : '?'}pixiTest=1&pixiSeconds=10`
  : baseUrl

async function main() {
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForSelector('canvas.pixiRaceCanvas', { timeout: 20_000 })
  await page.waitForTimeout(2500)

  const metrics = await page.evaluate(() => ({
    engine: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    canvasCount: document.querySelectorAll('canvas.pixiRaceCanvas').length,
    mirrorCount: document.querySelectorAll('.battlePixiHitMirror, .pixiHitTargetMirror').length,
    warning: document.querySelector('[data-qid="battle:pixi:validation-warning"]')?.textContent ?? null,
  }))

  const shot = resolve(outDir, 'battle-pixi-sanity.png')
  await page.screenshot({ path: shot, fullPage: false })
  await browser.close()

  if (errors.length) {
    console.error('console/page errors:', errors.slice(0, 5).join('\n'))
    process.exit(1)
  }
  if (!metrics.engine || metrics.canvasCount < 1) {
    console.error('Pixi engine did not mount', metrics)
    process.exit(1)
  }

  console.log('PASS battle-pixi-sanity')
  console.log(JSON.stringify({ url, metrics, screenshot: shot }, null, 2))
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
