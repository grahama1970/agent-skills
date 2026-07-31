#!/usr/bin/env node
/**
 * Retirement proof: battle-004-kill-shot stays fail-closed until a real
 * Judge-backed kill receipt producer exists.
 */
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const unsupportedPath = resolve(
  root,
  'public/battle-fixtures/battle-004-kill-shot-pixi-replay/unsupported.json',
)
const removedFixturePath = resolve(
  root,
  'public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json',
)

const marker = JSON.parse(await readFile(unsupportedPath, 'utf8'))
const routeRegistry = await readFile(resolve(root, 'src/lib/battle-receipt-replay.ts'), 'utf8')
const routeIsRetired = routeRegistry.includes(
  '"battle-004-kill-shot": "/battle-fixtures/battle-004-kill-shot-pixi-replay/unsupported.json"',
)

const checks = [
  {
    id: 'unsupported-marker-retired',
    pass: marker.schema === 'battle.unsupported_fixture.v1' && marker.status === 'RETIRED',
    detail: marker,
  },
  {
    id: 'old-route-does-not-silently-fallback',
    pass: routeIsRetired,
    detail: { routeIsRetired },
  },
  {
    id: 'normalized-kill-fixture-removed',
    pass: !(await exists(removedFixturePath)),
    detail: { removedFixturePath },
  },
]

const failed = checks.filter((check) => !check.pass)
console.log(JSON.stringify({ checks, failed: failed.length }, null, 2))
if (failed.length) process.exit(1)
console.log('BATTLE_PROVE_KILL_SHOT_RETIRED_PASS')

async function exists(path) {
  try {
    await readFile(path)
    return true
  } catch (error) {
    if (error && error.code === 'ENOENT') return false
    throw error
  }
}
