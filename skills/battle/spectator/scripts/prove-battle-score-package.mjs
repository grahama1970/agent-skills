#!/usr/bin/env node
import { mkdir, readFile, writeFile, readdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_SCORE_PROOF_DIR ?? '/tmp/battle-score-package-proof')
const root = resolve(process.cwd(), 'public/battle-audio')
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

await mkdir(outDir, { recursive: true })

const cues = [
  'battle_intro_death_clock_overture.ogg',
  'exploit_death_stinger.ogg',
  'exploit_victory_stinger.ogg',
  'next_battle_arena_level.ogg',
  'battle_started_background_loop.ogg',
]
for (const name of cues) {
  const bytes = await readFile(resolve(root, 'score/v1', name))
  record(`ogg-${name}`, bytes.length > 1000, String(bytes.length))
  const res = await fetch(`${host}/battle-audio/score/v1/${name}`)
  record(`http-${name}`, res.ok, String(res.status))
}

const motifs = await readdir(resolve(root, 'score/v1/motifs'))
const oggMotifs = motifs.filter((name) => name.endsWith('.ogg'))
record('motif-count-12', oggMotifs.length === 12, String(oggMotifs.length))
for (const name of oggMotifs) {
  const res = await fetch(`${host}/battle-audio/score/v1/motifs/${name}`)
  record(`motif-http-${name}`, res.ok, String(res.status))
}

const catalog = JSON.parse(await readFile(resolve(root, 'score/v1/runtime-catalog.json'), 'utf8'))
record('catalog-schema', catalog.schema === 'battle.music_runtime_catalog.v1', catalog.schema)
record('catalog-provisional', catalog.provisional_gm_render === true, String(catalog.provisional_gm_render))
record('catalog-legacy-not-selectable', catalog.legacy_intro_selectable === false, String(catalog.legacy_intro_selectable))
record('catalog-fail-closed', catalog.fail_closed === true, String(catalog.fail_closed))

const midiCue = await readFile(resolve(root, 'score/midi/cues/battle_intro_death_clock_overture.mid'))
record('midi-source-present', midiCue.slice(0, 4).toString() === 'MThd', String(midiCue.length))
const legacy = await readFile(resolve(root, 'legacy/battle-004-round-intro.mid'))
record('legacy-genesis-midi', legacy.slice(0, 4).toString() === 'MThd', String(legacy.length))

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify({ host, mocked: false, live: 'static_score_assets_http', provisional_gm_render: true, checks, failed: failed.map((i) => i.id), passCount: checks.length - failed.length, total: checks.length }, null, 2),
)
if (failed.length) {
  console.error(`prove:score-package FAILED ${failed.length}/${checks.length}`)
  process.exit(1)
}
console.log(`prove:score-package PASS ${checks.length}/${checks.length}`)
