import './ssr_dom_shim'
// @ts-expect-error resolved by esbuild alias in board_media_mix_live.mjs
import { dreamMemoryResultFromDocument, dreamMemoryResultPriority, dreamMemoryStratum, stratifiedMemorySample } from 'pd-ui-memory'

const MEMORY_API = process.env.PD_MEMORY_API ?? 'http://127.0.0.1:3001'
const IDEA = "Embry and Kai both faked a sick day at their summer jobs to go surfing on the Big Island on a Wednesday in June of 2024 — Kona Coast, Kahalu'u Bay, summer swell patterns, lava rock reefs, local surf etiquette."

async function main(): Promise<void> {
  let recall: Response
  try {
    recall = await fetch(`${MEMORY_API}/api/memory/recall`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: `Embry Kai surf Big Island media contact sheets audio video ${IDEA}`, collections: ['persona_memory'], tags: ['persona:embry'], k: 24 }),
    })
  } catch {
    console.log('BLOCKED_MEMORY_API_UNREACHABLE')
    process.exit(0)
  }
  if (!recall.ok) { console.error(`RECALL_HTTP_${recall.status}`); process.exit(1) }
  const recallData = await recall.json() as Record<string, unknown>
  const nodes = (recallData.items ?? recallData.results ?? []) as Array<Record<string, unknown>>
  if (nodes.length === 0) { console.error('RECALL_EMPTY'); process.exit(1) }

  const keys = nodes.map((n) => String(n._key ?? '')).filter(Boolean)
  const byKeys = await fetch(`${MEMORY_API}/api/memory/recall/by-keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ collection: 'persona_memory', keys }),
  })
  if (!byKeys.ok) { console.error(`BY_KEYS_HTTP_${byKeys.status}`); process.exit(1) }
  const docs = ((await byKeys.json()) as Record<string, unknown>).documents as Array<Record<string, unknown>>

  const results = docs.map((doc, i) => dreamMemoryResultFromDocument(doc, i))
  // PD_ORDERING=pinned reproduces the pre-fix hardcoded ordering so the
  // regression record can prove this guard fails against the old behavior.
  const board = process.env.PD_ORDERING === 'pinned'
    ? [...results].sort((a, b) => dreamMemoryResultPriority(a) - dreamMemoryResultPriority(b)).slice(0, 12)
    : stratifiedMemorySample(results, 24, IDEA).slice(0, 12)
  const strata = { image: 0, video: 0, audio: 0, text: 0 } as Record<string, number>
  for (const card of board) strata[dreamMemoryStratum(card)] += 1

  console.log(`BOARD_STRATA image=${strata.image} video=${strata.video} audio=${strata.audio} text=${strata.text}`)
  const missing = ['image', 'video', 'audio'].filter((s) => strata[s] === 0)
  if (missing.length > 0) { console.error(`BOARD_MISSING_STRATA: ${missing.join(', ')}`); process.exit(1) }
  console.log('BOARD_MEDIA_MIX_OK')
}

main().catch((err) => { console.error(`PROBE_ERROR: ${err instanceof Error ? err.message : String(err)}`); process.exit(1) })
