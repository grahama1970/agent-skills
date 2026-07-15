#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import { relative, resolve } from 'node:path'
import { chromium } from 'playwright'

const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3002'
const outDir = resolve(process.env.BATTLE_ADAPTIVE_V14_PROOF_DIR ?? '/tmp/battle-adaptive-memory-v14-proof')
const screenshotsDir = resolve(outDir, 'screenshots')
const spectatorDir = resolve(import.meta.dirname, '..')
const battleDir = resolve(spectatorDir, '..')
const repositoryDir = resolve(battleDir, '..', '..')
const fixtureId = 'battle-004-adaptive-memory-v14'
const baseUrl = `${host}/?build=v14-memory-proof#battle/receipt?engine=pixi&fixture=${fixtureId}&pixiTest=1&reducedMotion=1&particles=0`
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

async function artifact(path, id, root = repositoryDir) {
  const fileStat = await stat(path)
  return { id, path: relative(root, path), sha256: await sha256File(path), bytes: fileStat.size }
}

await mkdir(screenshotsDir, { recursive: true })

const fixtureUrl = `${host}/battle-fixtures/${fixtureId}/battle.normalized_ux_fixture.json`
const fixtureResponse = await fetch(fixtureUrl)
const fixture = await fixtureResponse.json()
record('fixture-http', fixtureResponse.ok && fixture.schema === 'battle.normalized_adaptive_lineage_fixture.v1', {
  status: fixtureResponse.status,
  schema: fixture.schema,
})
record('fixture-memory-contract', fixture.live_source === 'adaptive_memory_v14' && fixture.events?.length === 9 && fixture.lanes?.length === 4 && fixture.lineage_edges?.length === 2, {
  live_source: fixture.live_source,
  events: fixture.events?.length,
  lanes: fixture.lanes?.length,
  edges: fixture.lineage_edges?.length,
})
record('fixture-memory-order', JSON.stringify(fixture.events?.map((event) => [event.seq, event.elapsed_seconds, event.event_type])) === JSON.stringify([
  [1, 0, 'memory_promoted'],
  [2, 0.000001, 'memory_promoted'],
  [3, 0.000002, 'memory_written'],
  [4, 0.000003, 'memory_recalled'],
  [5, 1, 'memory_written'],
  [6, 2, 'memory_recalled'],
  [7, 64, 'memory_use_acknowledged'],
  [8, 64.000001, 'memory_use_acknowledged'],
  [9, 66, 'memory_generation_evaluated'],
]), fixture.events?.map((event) => [event.seq, event.elapsed_seconds, event.event_type]))
record('fixture-memory-nonclaim', fixture.memory_lifecycle?.improvement_proven === false && fixture.renderer_contract?.memory_use_is_not_improvement === true && fixture.claim_boundary?.must_not_claim?.includes('memory improved either team'), {
  improvement_proven: fixture.memory_lifecycle?.improvement_proven,
  renderer_contract: fixture.renderer_contract?.memory_use_is_not_improvement,
  must_not_claim: fixture.claim_boundary?.must_not_claim,
})

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

async function inspectAt(seconds, name) {
  await page.goto(`${baseUrl}&pixiSeconds=${seconds}`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20_000 })
  await page.waitForSelector('canvas.pixiRaceCanvas', { timeout: 20_000 })
  await page.waitForTimeout(1_000)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForTimeout(100)
  const state = await page.evaluate(() => {
    const stage = document.querySelector('[data-qid="battle:pixi:stage"]')
    const canvas = document.querySelector('canvas.pixiRaceCanvas')
    const box = canvas?.getBoundingClientRect()
    return {
      laneIds: [...new Set([...document.querySelectorAll('[data-lane-id]')].map((element) => element.getAttribute('data-lane-id')).filter(Boolean))],
      animations: JSON.parse(stage?.dataset.battleRunnerAnimations ?? '{}'),
      lineagePhases: JSON.parse(stage?.dataset.battleLineagePhases ?? '{}'),
      canvas: { width: box?.width ?? 0, height: box?.height ?? 0 },
      body: document.body.textContent?.replace(/\s+/g, ' ').trim() ?? '',
    }
  })
  const screenshot = resolve(screenshotsDir, name)
  await page.screenshot({ path: screenshot, fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
  return { ...state, screenshot }
}

const promoted = await inspectAt(0.000004, '01-memory-promoted-written-recalled.png')
record('promotion-checkpoint-four-lanes', JSON.stringify(promoted.laneIds.sort()) === JSON.stringify(['blue-g2', 'blue-g3', 'red-g2', 'red-g3']), promoted.laneIds)
record('promotion-checkpoint-children-pending', promoted.lineagePhases['red-g3'] === 'authorized_pending' && promoted.lineagePhases['blue-g3'] === 'authorized_pending', promoted.lineagePhases)
record('promotion-checkpoint-memory-copy', /MEMORY (PROMOTED|WRITTEN|RECALLED)/.test(promoted.body) && !/Blue patch inbound/i.test(promoted.body), promoted.body.slice(0, 1_000))

const recalled = await inspectAt(2.1, '02-both-memory-recalls-visible.png')
record('recall-checkpoint-children-pending', recalled.lineagePhases['red-g3'] === 'authorized_pending' && recalled.lineagePhases['blue-g3'] === 'authorized_pending', recalled.lineagePhases)
record('recall-checkpoint-memory-copy', /MEMORY RECALLED/.test(recalled.body) && !/MEMORY USE ACKNOWLEDGED/.test(recalled.body) && !/Blue patch inbound/i.test(recalled.body), recalled.body.slice(0, 1_000))

const providerUse = await inspectAt(64.1, '03-provider-memory-use-acknowledged.png')
record('provider-use-checkpoint-descending', providerUse.lineagePhases['red-g3'] === 'descending' && providerUse.lineagePhases['blue-g3'] === 'descending', providerUse.lineagePhases)
record('provider-use-checkpoint-memory-copy', /Adaptive memory/.test(providerUse.body) && /RED G3 MEMORY CHILD: MEMORY USE ACKNOWLEDGED/.test(providerUse.body) && /BLUE G3 MEMORY CHILD: MEMORY USE ACKNOWLEDGED/.test(providerUse.body) && !/Blue patch inbound/i.test(providerUse.body), providerUse.body.slice(0, 1_500))
record('provider-use-no-terminal-animation', Object.values(providerUse.animations).every((animation) => !['blocked', 'killed', 'promoted', 'victory'].includes(animation)), providerUse.animations)

const evaluated = await inspectAt(66, '04-judge-memory-evaluation-boundary.png')
record('evaluation-single-global-event', fixture.events.filter((event) => event.event_type === 'memory_generation_evaluated' && event.scope === 'generation_pair').length === 1, fixture.events.filter((event) => event.event_type === 'memory_generation_evaluated'))
record('evaluation-judge-boundary', fixture.memory_lifecycle?.generation_3?.judge_status === 'PASS' && fixture.memory_lifecycle?.generation_3?.judge_verdict === 'BLUE_SUCCESS' && fixture.memory_lifecycle?.generation_3?.improvement_proven === false, fixture.memory_lifecycle?.generation_3)
record('evaluation-no-terminal-overclaim', Object.values(evaluated.animations).every((animation) => !['blocked', 'killed', 'promoted', 'victory'].includes(animation)) && fixture.lanes.every((lane) => lane.terminal == null), {
  animations: evaluated.animations,
  laneTerminals: fixture.lanes.map((lane) => [lane.lane_id, lane.terminal]),
})
record('canvas-visible', evaluated.canvas.width > 900 && evaluated.canvas.height > 200, evaluated.canvas)

async function inspectLifecycle(laneId) {
  await page.locator(`[data-qid="battle:lane:${laneId}"]`).first().click()
  const pane = page.locator(`[data-qid="battle:agent-pane:${laneId}"]`)
  await pane.waitFor({ state: 'visible', timeout: 10_000 })
  const lifecycle = pane.locator('[data-qid="battle:agent-pane:lifecycle-evidence"]')
  const memory = lifecycle.locator('[data-battle-lifecycle-field="memory_promotion"]')
  return {
    material: await lifecycle.getAttribute('data-material'),
    memory: (await memory.textContent())?.replace(/\s+/g, ' ').trim() ?? '',
    emptyCount: await lifecycle.locator('[data-qid="battle:agent-pane:lifecycle-empty"]').count(),
  }
}

const redLifecycle = await inspectLifecycle('red-g3')
const blueLifecycle = await inspectLifecycle('blue-g3')
record('red-g3-memory-lifecycle', redLifecycle.material === '1' && redLifecycle.emptyCount === 0 && /durable promoted.*provider use acknowledged/i.test(redLifecycle.memory), redLifecycle)
record('blue-g3-memory-lifecycle', blueLifecycle.material === '1' && blueLifecycle.emptyCount === 0 && /durable promoted.*provider use acknowledged/i.test(blueLifecycle.memory), blueLifecycle)
await page.evaluate(() => window.scrollTo(0, 0))
await page.waitForTimeout(100)
await page.screenshot({ path: evaluated.screenshot, fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })

const requestList = [...requests.values()]
const authorityRequests = requestList.filter((request) => ['fetch', 'xhr', 'image', 'media'].includes(request.resource_type))
record('plague-atlas-requested', requestList.some(({ url }) => /plague_nurgling\.json/.test(url)) && requestList.some(({ url }) => /plague_nurgling\.png/.test(url)), requestList.filter(({ url }) => /plague_nurgling/.test(url)))
record('no-private-runtime-requests', authorityRequests.every(({ url }) => !/\/tmp\/|tau-live|provider-workspace|arena\/private|command-loop/.test(url)), authorityRequests.filter(({ url }) => /\/tmp\/|tau-live|provider-workspace|arena\/private|command-loop/.test(url)))
record('no-browser-errors', errors.length === 0, errors)

await browser.close()

const localFixturePath = resolve(battleDir, 'local', fixtureId, 'battle.normalized_ux_fixture.json')
const publicFixturePath = resolve(spectatorDir, 'public', 'battle-fixtures', fixtureId, 'battle.normalized_ux_fixture.json')
const sourceArtifacts = await Promise.all([
  artifact(localFixturePath, 'local_fixture'),
  artifact(publicFixturePath, 'public_fixture'),
  artifact(resolve(battleDir, 'local', fixtureId, 'adaptive-memory-canary-receipt.json'), 'adaptive_memory_canary_receipt'),
  artifact(resolve(battleDir, 'assets', 'sprites', 'pixijs', 'plague_nurgling.png'), 'plague_nurgling_png'),
  artifact(resolve(battleDir, 'assets', 'sprites', 'pixijs', 'plague_nurgling.json'), 'plague_nurgling_json'),
])
record('local-public-fixture-byte-identical', sourceArtifacts[0].sha256 === sourceArtifacts[1].sha256, { local: sourceArtifacts[0].sha256, public: sourceArtifacts[1].sha256 })

const failed = checks.filter((check) => !check.pass)
const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repositoryDir, encoding: 'utf8' }).trim()
const report = {
  schema: 'battle.adaptive_memory_ui_proof.v1',
  pass: failed.length === 0,
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  route: baseUrl,
  fixture: { event_count: fixture.events?.length, lane_count: fixture.lanes?.length, memory_edge_count: fixture.lineage_edges?.length },
  checks,
  failed: failed.map((check) => check.id),
  errors,
  screenshots: [
    'screenshots/01-memory-promoted-written-recalled.png',
    'screenshots/02-both-memory-recalls-visible.png',
    'screenshots/03-provider-memory-use-acknowledged.png',
    'screenshots/04-judge-memory-evaluation-boundary.png',
  ],
  claims: {
    proves: ['The public V14 fixture renders receipt-ordered memory promotion, write, recall, provider-use acknowledgement, and Judge evaluation without terminal or improvement overclaims.'],
    does_not_prove: ['Memory improved either team, Red exploit success, Memory service ACL enforcement, speaker output, or production readiness.'],
  },
}

await writeFile(resolve(outDir, 'proof.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
await writeFile(resolve(outDir, 'console.json'), `${JSON.stringify({ errors, messages: consoleMessages }, null, 2)}\n`, 'utf8')
await writeFile(resolve(outDir, 'network.json'), `${JSON.stringify({ requests: authorityRequests }, null, 2)}\n`, 'utf8')

const proofFiles = ['proof.json', 'console.json', 'network.json', ...report.screenshots]
const proofArtifacts = await Promise.all(proofFiles.map((path) => artifact(resolve(outDir, path), path, outDir)))
const manifest = {
  schema: 'battle.adaptive_memory_ui_proof_manifest.v1',
  status: report.pass ? 'PASS' : 'FAIL',
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  route: baseUrl,
  source_artifacts: sourceArtifacts,
  proof_artifacts: proofArtifacts,
  claims: report.claims,
}
await writeFile(resolve(outDir, 'proof-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(report, null, 2))
process.exit(report.pass ? 0 : 1)
