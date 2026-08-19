/** Dev host for the persona-dream pipeline API.
 *
 * The pipeline workspace (ui/src/DreamWorkspace.tsx) reads
 * /api/projects/dream/*, served by server/src (an express Router with no
 * standalone binary). This host mounts that router for local development;
 * vite.config.ts proxies /api/projects/dream here. Same pattern as the
 * receipted e2e host in reports/goal_v5/emotion_proof/http_host_e2e/boot.ts.
 */
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import express from 'express'
import { createPersonaDreamRouter } from '../../../server/src/index'

const here = dirname(fileURLToPath(import.meta.url))
const skillRoot = resolve(here, '../../..')

const outputRoot = '/mnt/storage12tb/skills/persona-dream/outputs'
const voiceRefs = resolve(skillRoot, '../../../chatterbox/persona_dream_voice_refs')
// Persona memory documents reference their media under this root (see
// persona_memory.media_asset.v1 source_path values).
const personaMedia = '/mnt/storage12tb/media/personas'

const app = express()
app.use(express.json({ limit: '4mb' }))
app.use(
  '/api/projects/dream',
  createPersonaDreamRouter({
    reportRoots: [resolve(skillRoot, 'reports')],
    outputRoots: existsSync(outputRoot) ? [outputRoot] : [],
    assetRoots: [voiceRefs, personaMedia].filter((p) => existsSync(p)),
  }),
)

const port = Number(process.env.DREAM_API_PORT ?? 8791)
app.listen(port, '127.0.0.1', () => console.log(`dream api host listening on 127.0.0.1:${port}`))
