#!/usr/bin/env node
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const sparsePath = resolve(__dirname, '../../local/battle-004-sparse.normalized.json')
const sparse = JSON.parse(readFileSync(sparsePath, 'utf8'))

const checks = []
function record(id, pass, detail) {
  checks.push({ id, pass, detail })
}

record('sparse-lineage-missing', sparse.lineage?.mode === 'missing', sparse.lineage?.mode)
record('sparse-no-spawn-count', Number(sparse.lineage?.spawn_count ?? 0) === 0, sparse.lineage?.spawn_count)
record('sparse-single-lane', (sparse.lanes ?? []).length === 1, (sparse.lanes ?? []).map((l) => l.id))
record('sparse-no-child-lanes', !(sparse.lanes ?? []).some((l) => l.parentId), (sparse.lanes ?? []).map((l) => l.id))

const pass = checks.every((c) => c.pass)
console.log(JSON.stringify({ pass, checks, mocked: false, live: false, fixture: sparsePath }, null, 2))
process.exit(pass ? 0 : 1)
