import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import test from 'node:test'
import { createBraveResearchPort } from '../src/services/brave'
import { createDefaultResearchPort } from '../src/services/defaults'
import { createChatterboxVoiceAuditionPort } from '../src/services/voiceAudition'

test('Chatterbox audition resolves container /out paths through the host output mount', async () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-chatterbox-mount-'))
  const references = resolve(root, 'references')
  const generated = resolve(root, 'generated')
  const output = resolve(root, 'output')
  mkdirSync(references)
  mkdirSync(generated)
  mkdirSync(output)
  const referencePath = resolve(references, 'kai.wav')
  writeFileSync(referencePath, 'reference')
  writeFileSync(resolve(generated, 'exact-line.wav'), 'generated audio')
  const port = createChatterboxVoiceAuditionPort({
    agentUrl: 'http://127.0.0.1:8018',
    outputRoot: output,
    allowedReferenceRoots: [references],
    hostOutputRoot: generated,
    hostReferenceRoot: references,
    containerReferenceRoot: '/work/persona_dream_voice_refs',
    fetchImpl: (async () => new Response(JSON.stringify({
      ok: true,
      audio: '/out/exact-line.wav',
      duration_seconds: 2,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })) as typeof fetch,
  })
  const result = await port.audition({
    character: 'kai',
    text: "If we paddle now, we're cutting across the lineup.",
    refAudioPath: referencePath,
    tone: 'calm_precise',
  })
  assert.equal(result.status, 'ok')
  assert.match(result.audioPath, /dream-voice-auditions\/.*-kai-/)
  rmSync(root, { recursive: true, force: true })
})

test('Brave adapter normalizes bounded results without leaking credentials', async () => {
  let observedUrl = ''
  let observedToken = ''
  const port = createBraveResearchPort({
    apiKey: 'secret-test-token',
    resultCount: 2,
    fetchImpl: (async (input, init) => {
      observedUrl = String(input)
      observedToken = String((init?.headers as Record<string, string>)['X-Subscription-Token'])
      return new Response(JSON.stringify({ web: { total: 3, results: [
        { title: 'A', url: 'https://a.example', description: 'first' },
        { title: 'B', url: 'https://b.example', description: 'second' },
        { title: 'C', url: 'https://c.example', description: 'third' },
      ] } }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }) as typeof fetch,
  })
  const result = await port.search('Embry surf')
  assert.equal(new URL(observedUrl).origin, 'https://api.search.brave.com')
  assert.equal(new URL(observedUrl).searchParams.get('count'), '2')
  assert.equal(observedToken, 'secret-test-token')
  assert.deepEqual(result.results, [
    { title: 'A', url: 'https://a.example', snippet: 'first' },
    { title: 'B', url: 'https://b.example', snippet: 'second' },
  ])
  assert.equal(JSON.stringify(result).includes('secret-test-token'), false)
})

test('default research port fails closed when no API key is configured', async () => {
  await assert.rejects(() => createDefaultResearchPort({}).search('query'), /brave_search_api_key_not_configured/)
})

test('Brave adapter rejects a noncanonical endpoint', async () => {
  const port = createBraveResearchPort({ apiKey: 'test', endpoint: new URL('https://example.com/search') })
  await assert.rejects(() => port.search('query'), /brave_search_endpoint_not_allowed/)
})
