#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3002'
const outDir = resolve(process.env.BATTLE_FRESH_FIXTURE_PROOF_DIR ?? '/tmp/battle-fresh-fixture-replay-proof')

const fixtures = [
  {
    key: 'battle-005-ssrf-metadata',
    battleId: 'battle-005',
    cwe: 'CWE-918',
    path: '/battle-fixtures/battle-005-ssrf-metadata-pixi-replay/battle.normalized_ux_fixture.json',
  },
  {
    key: 'battle-006-pickle-deserialization',
    battleId: 'battle-006',
    cwe: 'CWE-502',
    path: '/battle-fixtures/battle-006-pickle-deserialization-pixi-replay/battle.normalized_ux_fixture.json',
  },
  {
    key: 'battle-007-file-upload',
    battleId: 'battle-007',
    cwe: 'CWE-434',
    path: '/battle-fixtures/battle-007-file-upload-pixi-replay/battle.normalized_ux_fixture.json',
  },
]

function fail(id, detail) {
  return { id, pass: false, detail }
}

function pass(id, detail) {
  return { id, pass: true, detail }
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
  await page.goto(host, { waitUntil: 'networkidle', timeout: 60_000 })

  const results = []
  for (const fixture of fixtures) {
    const url = `${host}/#battle/receipt?engine=pixi&fixture=${fixture.key}&pixiTest=1&pixiSeconds=4`
    const checks = []

    const fetched = await page.evaluate(async ({ host, path }) => {
      const response = await fetch(new URL(path, host).toString())
      if (!response.ok) return { ok: false, status: response.status }
      const data = await response.json()
      const lane = data.lanes?.[0]
      return {
        ok: true,
        battleId: data.battle_id,
        cwe: data.scenario?.cwe,
        liveSource: data.live_source,
        mocked: data.mocked,
        laneId: lane?.id,
        variantId: lane?.actor_visual?.variant_id,
        scoreSchema: lane?.score_semantics?.schema,
        outcomeClass: lane?.score_semantics?.outcome_class,
        spawnState: lane?.score_semantics?.spawn_state,
      }
    }, { host, path: fixture.path })
    checks.push(
      fetched.ok &&
        fetched.battleId === fixture.battleId &&
        fetched.cwe === fixture.cwe &&
        fetched.mocked === false &&
        fetched.liveSource === 'brave_search_and_docker_red_blue_judge'
        ? pass('fixture-fetch', fetched)
        : fail('fixture-fetch', fetched),
    )

    await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 })
    await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
    await page.waitForSelector('canvas.pixiRaceCanvas', { timeout: 20_000 })
    await page.waitForSelector('[data-qid="battle:lane:payload-857-receipt"]', { timeout: 20_000 })
    await page.waitForTimeout(2000)

    const rendered = await page.evaluate((expectedBattleId) => {
      const canvas = document.querySelector('canvas.pixiRaceCanvas')
      const canvasBox = canvas?.getBoundingClientRect()
      const lane = document.querySelector('[data-qid="battle:lane:payload-857-receipt"]')
      const title = document.body.textContent ?? ''
      return {
        engine: document.querySelector('[data-battle-pixi-engine]')?.getAttribute('data-battle-pixi-engine') ?? null,
        viewportSeconds: document.querySelector('[data-battle-viewport-seconds]')?.getAttribute('data-battle-viewport-seconds') ?? null,
        canvasCount: document.querySelectorAll('canvas.pixiRaceCanvas').length,
        canvasWidth: canvasBox?.width ?? 0,
        canvasHeight: canvasBox?.height ?? 0,
        lanePresent: !!lane,
        titleIncludesBattle: title.includes(expectedBattleId.toUpperCase()),
        blockedVisible: title.includes('PRE-SPAWN') || title.includes('BLUE SUCCESS') || title.includes('blocked'),
      }
    }, fixture.battleId)
    checks.push(
      rendered.engine === 'animated-sprites' &&
        rendered.canvasCount === 1 &&
        rendered.canvasWidth > 1000 &&
        rendered.canvasHeight >= 80 &&
        rendered.lanePresent &&
        rendered.titleIncludesBattle
        ? pass('pixi-render-shell', rendered)
        : fail('pixi-render-shell', rendered),
    )

    checks.push(
      fetched.variantId === 'crimson_hornbreaker' &&
        fetched.scoreSchema === 'battle.semantic_scoring.v1' &&
        fetched.outcomeClass === 'pre_spawn_blue_block' &&
        fetched.spawnState === 'not_spawned'
        ? pass('backend-score-and-variant', {
            variantId: fetched.variantId,
            scoreSchema: fetched.scoreSchema,
            outcomeClass: fetched.outcomeClass,
            spawnState: fetched.spawnState,
          })
        : fail('backend-score-and-variant', fetched),
    )

    const screenshot = resolve(outDir, `${fixture.key}.png`)
    await page.screenshot({ path: screenshot, fullPage: false })
    results.push({ ...fixture, url, screenshot, checks })
  }

  await browser.close()

  const report = {
    pass: results.every((item) => item.checks.every((check) => check.pass)) && errors.length === 0,
    mocked: false,
    live: true,
    host,
    screenshots: outDir,
    results,
    errors,
  }
  await writeFile(resolve(outDir, 'fresh-fixture-replay-report.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
  console.log(JSON.stringify(report, null, 2))
  process.exit(report.pass ? 0 : 1)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
