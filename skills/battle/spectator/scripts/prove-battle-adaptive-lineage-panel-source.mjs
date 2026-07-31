#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import { relative, resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_ADAPTIVE_PANEL_SOURCE_PROOF_DIR ?? '/tmp/battle-adaptive-lineage-panel-source-proof')
const screenshotsDir = resolve(outDir, 'screenshots')
const spectatorDir = resolve(import.meta.dirname, '..')
const battleDir = resolve(spectatorDir, '..')
const repositoryDir = resolve(battleDir, '..', '..')
const checks = []
const errors = []

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

async function publicFixtureArtifact(id) {
  return artifact(
    resolve(spectatorDir, 'public', 'battle-fixtures', id, 'battle.normalized_ux_fixture.json'),
    `${id}:public_fixture`,
  )
}

await mkdir(screenshotsDir, { recursive: true })

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(message.text())
})

async function inspect(fixtureId, screenshotName) {
  const url = `${host}/#battle/receipt?engine=pixi&fixture=${fixtureId}&pixiTest=1&reducedMotion=1&particles=0`
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 })
  await page.waitForSelector('[data-qid="battle:lineage-comparison"]', { timeout: 20_000 })
  await page.waitForSelector('[data-qid="battle:race:source"]', { timeout: 20_000 })
  await page.waitForTimeout(500)
  const screenshot = resolve(screenshotsDir, screenshotName)
  const screenshotRelative = relative(outDir, screenshot)
  await page.screenshot({ path: screenshot, fullPage: false, animations: 'disabled', caret: 'hide', scale: 'css' })
  return page.evaluate((capturedScreenshot) => {
    const panel = document.querySelector('[data-qid="battle:lineage-comparison"]')
    const race = document.querySelector('[data-qid="battle:race:source"]')
    const badge = document.querySelector('[data-qid="battle:adaptive-lineage:badge"]')
    const body = document.body.textContent?.replace(/\s+/g, ' ').trim() ?? ''
    return {
      panel: {
        mode: panel?.getAttribute('data-mode') ?? null,
        battleId: panel?.getAttribute('data-battle-id') ?? null,
        runId: panel?.getAttribute('data-run-id') ?? null,
        proofId: panel?.getAttribute('data-source-proof-id') ?? null,
        fixtureId: panel?.getAttribute('data-source-fixture-id') ?? null,
        sha256: panel?.getAttribute('data-source-fixture-sha256') ?? null,
        provesLive: panel?.getAttribute('data-proves-live') ?? null,
      },
      race: {
        battleId: race?.getAttribute('data-battle-id') ?? null,
        runId: race?.getAttribute('data-run-id') ?? null,
        proofId: race?.getAttribute('data-source-proof-id') ?? null,
        fixtureId: race?.getAttribute('data-source-fixture-id') ?? null,
        sha256: race?.getAttribute('data-source-fixture-sha256') ?? null,
      },
      badge: {
        text: badge?.textContent?.replace(/\s+/g, ' ').trim() ?? null,
        dataSource: badge?.getAttribute('data-data-source') ?? null,
        provesLive: badge?.getAttribute('data-proves-live') ?? null,
      },
      canonicalNodes: [...document.querySelectorAll('[data-qid^="battle:adaptive-lineage:canonical-node:"]')]
        .map((node) => node.getAttribute('data-source-lane-id')),
      unavailableReason: document.querySelector('[data-qid="battle:adaptive-lineage:unavailable-reason"]')?.textContent?.replace(/\s+/g, ' ').trim() ?? null,
      bodyHasStaticLiveFixtureText: /G1-A|G1-B|failure_guided_crossover/.test(body),
      bodyHasLiveBadge: /\bLIVE\b/.test(body),
      screenshot: capturedScreenshot,
    }
  }, screenshotRelative)
}

const [v13Artifact, v14Artifact] = await Promise.all([
  publicFixtureArtifact('battle-004-adaptive-lineage-v13'),
  publicFixtureArtifact('battle-004-adaptive-memory-v14'),
])
const v13 = await inspect('battle-004-adaptive-lineage-v13', '01-v13-source-bound-panel.png')
const v14 = await inspect('battle-004-adaptive-memory-v14', '02-v14-proof-unavailable-panel.png')

record('v13-race-panel-source-match',
  v13.panel.battleId === v13.race.battleId &&
    v13.panel.runId === v13.race.runId &&
    v13.panel.proofId === v13.race.proofId &&
    v13.panel.sha256 === v13.race.sha256,
  { panel: v13.panel, race: v13.race },
)
record('v13-source-hash-matches-public-fixture', v13.panel.sha256 === v13Artifact.sha256, {
  panel: v13.panel.sha256,
  publicFixture: v13Artifact.sha256,
})
record('v13-canonical-dual-team-mechanics', v13.panel.mode === 'canonical-dual-team' &&
  JSON.stringify(v13.canonicalNodes.sort()) === JSON.stringify(['blue-g1', 'blue-g2', 'red-g1', 'red-g2']),
  { mode: v13.panel.mode, nodes: v13.canonicalNodes },
)
record('v13-no-static-live-fixture-leak', !v13.bodyHasStaticLiveFixtureText && v13.badge.text !== 'LIVE' && v13.badge.provesLive === 'false', v13.badge)

record('v14-race-panel-source-match',
  v14.panel.battleId === v14.race.battleId &&
    v14.panel.runId === v14.race.runId &&
    v14.panel.proofId === v14.race.proofId &&
    v14.panel.sha256 === v14.race.sha256,
  { panel: v14.panel, race: v14.race },
)
record('v14-source-hash-matches-public-fixture', v14.panel.sha256 === v14Artifact.sha256, {
  panel: v14.panel.sha256,
  publicFixture: v14Artifact.sha256,
})
record('v14-switches-away-from-v13-source', v14.panel.runId !== v13.panel.runId && v14.panel.sha256 !== v13.panel.sha256, {
  v13: v13.panel,
  v14: v14.panel,
})
record('v14-fails-closed-with-visible-unavailable-state', v14.panel.mode === 'proof-unavailable' && /does not emit canonical dual-team mechanics_trees/i.test(v14.unavailableReason ?? ''), {
  mode: v14.panel.mode,
  reason: v14.unavailableReason,
})
record('v14-no-static-live-fixture-leak', !v14.bodyHasStaticLiveFixtureText && v14.badge.text !== 'LIVE' && v14.badge.provesLive === 'false', v14.badge)
record('no-browser-errors', errors.length === 0, errors)

await browser.close()

const failed = checks.filter((check) => !check.pass)
const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repositoryDir, encoding: 'utf8' }).trim()
const report = {
  schema: 'battle.adaptive_lineage_panel_source_proof.v1',
  pass: failed.length === 0,
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  checks,
  failed: failed.map((check) => check.id),
  states: { v13, v14 },
  source_artifacts: [v13Artifact, v14Artifact],
  screenshots: ['screenshots/01-v13-source-bound-panel.png', 'screenshots/02-v14-proof-unavailable-panel.png'],
  claims: {
    proves: [
      'The receipt-route adaptive mechanics panel is derived from the currently loaded fixture source metadata.',
      'V13 exposes canonical dual-team mechanics from its public fixture and V14 fails closed without retaining V13 or adaptive-lineage-live.json data.',
    ],
    does_not_prove: [
      'Live execution, Memory service correctness, or backend scoring changes.',
    ],
  },
}

await writeFile(resolve(outDir, 'proof.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
const proofArtifacts = await Promise.all([
  artifact(resolve(outDir, 'proof.json'), 'proof.json', outDir),
  artifact(resolve(outDir, 'screenshots/01-v13-source-bound-panel.png'), 'screenshots/01-v13-source-bound-panel.png', outDir),
  artifact(resolve(outDir, 'screenshots/02-v14-proof-unavailable-panel.png'), 'screenshots/02-v14-proof-unavailable-panel.png', outDir),
])
await writeFile(resolve(outDir, 'proof-manifest.json'), `${JSON.stringify({
  schema: 'battle.adaptive_lineage_panel_source_proof_manifest.v1',
  status: report.pass ? 'PASS' : 'FAIL',
  mocked: false,
  live: true,
  source_commit: sourceCommit,
  host,
  source_artifacts: report.source_artifacts,
  proof_artifacts: proofArtifacts,
  claims: report.claims,
}, null, 2)}\n`, 'utf8')

console.log(JSON.stringify(report, null, 2))
if (failed.length) process.exit(1)
console.log('BATTLE_PROVE_ADAPTIVE_LINEAGE_PANEL_SOURCE_PASS')
