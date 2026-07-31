#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const battleDir = resolve(__dirname, '../..')
const outDir = resolve(battleDir, 'docs/assets/screenshots/raw')
const host = await resolveBattleProveHost()

const shots = [
  {
    id: 'battle-004-spectator-replay',
    url: `${host}/#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn`,
    waitFor: '[data-battle-pixi-engine="animated-sprites"]',
    clipSelector: '.battle-mockup-shell',
  },
  {
    id: 'battle-004-lifecycle-cockpit',
    url: `${host}/#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn`,
    waitFor: '[data-qid="battle:agent-pane:lifecycle-evidence"]',
    clipSelector: '[data-qid="battle:agent-pane:lifecycle-evidence"]',
  },
  {
    id: 'battle-004-spawn-block-vfx',
    url: `${host}/#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn&pixiTest=1&pixiSeconds=99.4`,
    waitFor: '[data-battle-pixi-engine="animated-sprites"]',
    clipSelector: '.battle-mockup-shell',
  },
  {
    id: 'battle-004-pr3b-proof-card',
    url: `${host}/#battle/proof?fixture=battle-004-pr3b`,
    waitFor: '[data-qid="battle:proof-card:root"]',
    clipSelector: '[data-qid="battle:proof-card:root"]',
  },
]

await mkdir(outDir, { recursive: true })
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const manifest = []

for (const shot of shots) {
  await page.goto(shot.url, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector(shot.waitFor, { timeout: 20_000 })
  await page.waitForTimeout(1200)
  const pngPath = resolve(outDir, `${shot.id}.png`)
  const clip = shot.clipSelector ? await page.locator(shot.clipSelector).first().boundingBox() : null
  if (clip) {
    await page.screenshot({ path: pngPath, clip })
  } else {
    await page.screenshot({ path: pngPath })
  }
  const evidence = await page.evaluate(() => ({
    lifecycle: Boolean(document.querySelector('[data-qid="battle:agent-pane:lifecycle-evidence"]')),
    pixi: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
    text: document.querySelector('[data-qid="battle:agent-pane:lifecycle-evidence"]')?.textContent?.includes('knowledge_packet') ?? false,
  }))
  manifest.push({ id: shot.id, pngPath, url: shot.url, evidence })
}

await browser.close()
await writeFile(resolve(outDir, 'manifest.json'), JSON.stringify({ host, manifest }, null, 2))
console.log(JSON.stringify({ host, outDir, manifest }, null, 2))
