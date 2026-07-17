import type { DreamResearchPort, VoiceAuditionPort } from './contracts'
import { createBraveResearchPort } from './brave'
import { createChatterboxVoiceAuditionPort } from './voiceAudition'

const blockedResearch: DreamResearchPort = { async search() { throw new Error('brave_search_api_key_not_configured') } }
const blockedVoice: VoiceAuditionPort = { async audition() { throw new Error('chatterbox_voice_audition_not_configured') } }

export function createDefaultResearchPort(env: NodeJS.ProcessEnv = process.env): DreamResearchPort {
  const apiKey = env.BRAVE_SEARCH_API_KEY || env.BRAVE_API_KEY || ''
  return apiKey ? createBraveResearchPort({ apiKey }) : blockedResearch
}

export function createDefaultVoiceAuditionPort(options: { outputRoots: readonly string[]; assetRoots?: readonly string[] }, env: NodeJS.ProcessEnv = process.env): VoiceAuditionPort {
  const outputRoot = options.outputRoots[0]
  const allowedRoots = [...(options.assetRoots ?? []), ...options.outputRoots]
  if (!outputRoot || allowedRoots.length === 0) return blockedVoice
  try {
    return createChatterboxVoiceAuditionPort({
      agentUrl: env.CHATTERBOX_AGENT_URL ?? 'http://127.0.0.1:8018',
      outputRoot,
      allowedReferenceRoots: allowedRoots,
      hostOutputRoot: env.CHATTERBOX_HOST_OUT_DIR ?? '/home/graham/workspace/experiments/chatterbox/logs',
      hostReferenceRoot: env.CHATTERBOX_HOST_REF_DIR ?? '/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs',
      containerReferenceRoot: env.CHATTERBOX_CONTAINER_REF_DIR ?? '/work/persona_dream_voice_refs',
    })
  } catch {
    return blockedVoice
  }
}
