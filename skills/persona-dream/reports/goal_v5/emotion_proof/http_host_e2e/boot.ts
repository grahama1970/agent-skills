import express from 'express'
import { createPersonaDreamRouter } from '/home/graham/workspace/experiments/agent-skills/skills/persona-dream/server/src/index.ts'
const app = express()
app.use(express.json({ limit: '4mb' }))
app.use('/', createPersonaDreamRouter({
  reportRoots: ['/home/graham/workspace/experiments/agent-skills/skills/persona-dream/reports'],
  outputRoots: ['/tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/c0318d3c-2f9f-41b6-8596-efe36691b16f/scratchpad/hosttest/out'],
  assetRoots: ['/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs'],
}))
app.listen(3099, '127.0.0.1', () => console.log('LISTENING 3099'))
