import { basename } from 'node:path'

type ArtifactIndexEntry = {
  relative_path: string
  sha256: string
  roles: string[]
}

type RevisionArtifactIndex = {
  artifacts: Record<string, ArtifactIndexEntry>
}

type StoryboardFrame = {
  panelId: string
  role: 'start_frame' | 'end_frame'
  artifactId: string
  relativePath: string
  sha256: string
}

export type StoryboardConsumerProjection = {
  consumerContract: 'dream_storyboard_workspace_v1'
  panelCount: number
  panelIds: string[]
  frames: StoryboardFrame[]
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('BLOCKED_CONSUMER_CONTRACT:object_required')
  return value as Record<string, unknown>
}

export function hydrateStoryboardConsumer(
  packet: Record<string, unknown>,
  artifactIndex: RevisionArtifactIndex,
  expectedPanelCount = 4,
): StoryboardConsumerProjection {
  if (packet.schema !== 'persona_dream.storyboard_packet.v1' || packet.status !== 'PASS_PANEL_REVIEWED' || packet.accepted !== true) {
    throw new Error('BLOCKED_CONSUMER_CONTRACT:storyboard_packet_not_accepted')
  }
  if (!Array.isArray(packet.panels) || packet.panels.length !== expectedPanelCount || packet.panel_count !== packet.panels.length) {
    throw new Error('BLOCKED_CONSUMER_CONTRACT:storyboard_panel_count')
  }
  const panelIds: string[] = []
  const frames: StoryboardFrame[] = []
  for (const rawPanel of packet.panels) {
    const panel = object(rawPanel)
    const panelId = String(panel.panel_id ?? '')
    if (!panelId || panelIds.includes(panelId)) throw new Error('BLOCKED_CONSUMER_CONTRACT:storyboard_panel_id')
    panelIds.push(panelId)
    for (const role of ['start_frame', 'end_frame'] as const) {
      const frameContainer = object(panel[role])
      const acceptedFrame = object(frameContainer.accepted_frame)
      const sourcePath = String(acceptedFrame.path ?? '')
      const expectedSha256 = String(acceptedFrame.sha256 ?? '')
      const indexed = Object.entries(artifactIndex.artifacts).find(([, artifact]) =>
        artifact.relative_path.endsWith(`/generated_storyboard_frames/${basename(sourcePath)}`),
      )
      if (!indexed) throw new Error(`BLOCKED_ASSET_RESOLUTION:${panelId}:${role}`)
      const [artifactId, artifact] = indexed
      if (expectedSha256 !== artifact.sha256) throw new Error(`BLOCKED_ASSET_FETCH_HASH_MISMATCH:${panelId}:${role}`)
      frames.push({ panelId, role, artifactId, relativePath: artifact.relative_path, sha256: artifact.sha256 })
    }
  }
  if (frames.length !== expectedPanelCount * 2) throw new Error('BLOCKED_CONSUMER_CONTRACT:storyboard_frame_count')
  return { consumerContract: 'dream_storyboard_workspace_v1', panelCount: panelIds.length, panelIds, frames }
}
