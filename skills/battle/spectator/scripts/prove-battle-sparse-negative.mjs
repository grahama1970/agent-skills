#!/usr/bin/env node
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const sparsePath = resolve(
  __dirname,
  '../public/battle-fixtures/battle-004-sparse-pixi-replay/battle.normalized_ux_fixture.json',
)
const sparse = JSON.parse(readFileSync(sparsePath, 'utf8'))
const host = process.env.BATTLE_HOST ?? 'http://127.0.0.1:3002'
const publicUrl = `${host}/battle-fixtures/battle-004-sparse-pixi-replay/battle.normalized_ux_fixture.json`

const checks = []
function record(id, pass, detail) {
  checks.push({ id, pass, detail })
}

record('sparse-lineage-missing', sparse.lineage?.mode === 'missing', sparse.lineage?.mode)
record('sparse-no-spawn-count', Number(sparse.lineage?.spawn_count ?? 0) === 0, sparse.lineage?.spawn_count)
record('sparse-single-lane', (sparse.lanes ?? []).length === 1, (sparse.lanes ?? []).map((l) => l.id))
record('sparse-no-child-lanes', !(sparse.lanes ?? []).some((l) => l.parentId), (sparse.lanes ?? []).map((l) => l.id))

let publicOk = false
const requirePublic = process.env.BATTLE_REQUIRE_SPARSE_PUBLIC === '1'
try {
  const response = await fetch(publicUrl)
  publicOk = response.ok
  if (response.ok) {
    const remote = await response.json()
    record('sparse-public-route', remote.lineage?.mode === 'missing', publicUrl)
  } else if (requirePublic) {
    record('sparse-public-route', false, `${publicUrl} status ${response.status}`)
  }
} catch (error) {
  if (requirePublic) record('sparse-public-route', false, String(error))
}

const pass = checks.every((c) => c.pass)
console.log(JSON.stringify({ pass, checks, mocked: false, live: publicOk, fixture: sparsePath, publicUrl }, null, 2))
process.exit(pass ? 0 : 1)
