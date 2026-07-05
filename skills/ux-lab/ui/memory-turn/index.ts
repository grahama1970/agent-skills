export * from './MemoryTurnAdapter'

export {
  SpartaComplianceAdapter,
  classifySpartaTurn,
  isSpartaEvidenceBoundTurn,
  isSpartaGeneralUtilityTurn,
  safeArithmeticAnswer,
} from './SpartaComplianceAdapter'
export type { FetchLike as SpartaFetchLike, SpartaComplianceAdapterOptions } from './SpartaComplianceAdapter'

export { WatchChatAdapter } from './WatchChatAdapter'
export type {
  FetchLike as WatchFetchLike,
  WatchChatAdapterOptions,
  WatchChatAdapterProps,
  WatchSceneRow,
} from './WatchChatAdapter'

export { EmbryVoiceChatAdapter } from './EmbryVoiceChatAdapter'
export type {
  EmbryTurnAuthority,
  EmbryVoiceAudioAuthority,
  EmbryVoiceChatAdapterOptions,
  EmbryVoiceFetchLike,
} from './EmbryVoiceChatAdapter'

export { PersonaPlexAdapter } from './PersonaPlexAdapter'
export type {
  PersonaPlexAdapterOptions,
  PersonaPlexProtocolLike,
  PersonaPlexProtocolTurnArgs,
  WebSocketLike,
} from './PersonaPlexAdapter'

export * from './adapterRegistry'
