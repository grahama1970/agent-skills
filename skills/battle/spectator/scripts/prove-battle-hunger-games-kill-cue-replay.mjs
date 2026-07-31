#!/usr/bin/env node
/**
 * Retirement proof for the old HG kill-cue replay fixture.
 */
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const markerPath = resolve(
  import.meta.dirname,
  '../public/battle-fixtures/battle-004-kill-shot-pixi-replay/unsupported.json',
)
const marker = JSON.parse(await readFile(markerPath, 'utf8'))
const pass =
  marker.schema === 'battle.unsupported_fixture.v1' &&
  marker.status === 'RETIRED' &&
  String(marker.reason || '').includes('Judge-backed')

console.log(JSON.stringify({ markerPath, status: marker.status, pass }, null, 2))
if (!pass) process.exit(1)
console.log('BATTLE_PROVE_HG_KILL_CUE_REPLAY_RETIRED_PASS')
