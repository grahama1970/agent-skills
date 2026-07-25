import { createChatterboxVoiceAuditionPort } from '/home/graham/workspace/experiments/agent-skills/skills/persona-dream/server/src/services/voiceAudition.ts'
const port = createChatterboxVoiceAuditionPort({
  agentUrl: 'http://127.0.0.1:8018',
  outputRoot: '/tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/c0318d3c-2f9f-41b6-8596-efe36691b16f/scratchpad/audition_out',
  allowedReferenceRoots: ['/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs'],
  hostOutputRoot: '/home/graham/workspace/experiments/chatterbox/logs',
  hostReferenceRoot: '/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs',
  containerReferenceRoot: '/work/persona_dream_voice_refs',
})
const REF='/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs/embry_authorized_ref_30s_8s.wav'
const TEXT='I already told you where I stand. Do not ask me again.'
const cases = [
  {name:'wait_w02', tone:'wait_presence',  intensity:0.2},
  {name:'firm_w02', tone:'firm_boundary',  intensity:0.2},
  {name:'firm_w09', tone:'firm_boundary',  intensity:0.9},
]
for (const c of cases) {
  const r: any = await port.audition({character:'embry', text:TEXT, refAudioPath:REF, tone:c.tone, intensity:c.intensity})
  const engine = (r.emotionKnobs) ? 'has-knobs' : 'no-knobs'
  console.log('CASE '+JSON.stringify({name:c.name, tone:c.tone, intensity:c.intensity, knobs:r.emotionKnobs, audioPath:r.audioPath, receiptPath:r.receiptPath}))
}
