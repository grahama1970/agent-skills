#!/usr/bin/env node
/**
 * Retirement proof for the old receipt-director killed fixture.
 */
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const markerPath = resolve(
  import.meta.dirname,
  '../public/battle-fixtures/battle-004-kill-shot-pixi-replay/unsupported.json',
)
const marker = JSON.parse(await readFile(markerPath, 'utf8'))
const pass = marker.status === 'RETIRED' && marker.fixture_id === 'battle-004-kill-shot-pixi-replay'

console.log(JSON.stringify({ markerPath, fixture_id: marker.fixture_id, status: marker.status, pass }, null, 2))
if (!pass) process.exit(1)
console.log('BATTLE_PROVE_RECEIPT_DIRECTOR_KILLED_RETIRED_PASS')
