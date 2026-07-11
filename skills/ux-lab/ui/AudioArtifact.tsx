import React from 'react'
import { Volume2 } from 'lucide-react'

export type ReadOnlyAudioArtifact = {
  artifactId: string
  state: 'audio_ready'
  url: string
  sha256: string
  bytes: number
  contentType: string
  channels: number
  sampleRateHz: number
  durationMs: number
  playbackEnabled: false
}

export function AudioArtifact({ artifact }: { artifact: ReadOnlyAudioArtifact }): JSX.Element {
  return (
    <section
      data-qid={`shared-chat:audio:${artifact.artifactId}`}
      data-audio-state={artifact.state}
      data-audio-sha256={artifact.sha256}
      data-playback-enabled="false"
      style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 10, color: '#aeb8c6', fontSize: 11 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: '#dce5f3', fontWeight: 700 }}>
        <Volume2 size={14} aria-hidden="true" />
        <span>Audio ready · playback gate not enabled</span>
      </div>
      <div style={{ marginTop: 5, fontFamily: 'ui-monospace, monospace' }}>
        {artifact.bytes.toLocaleString()} bytes · {artifact.channels === 1 ? 'mono' : `${artifact.channels} channels`} · {artifact.sampleRateHz / 1000} kHz · {(artifact.durationMs / 1000).toFixed(2)} s
      </div>
      <div style={{ marginTop: 3, fontFamily: 'ui-monospace, monospace' }}>sha256 {artifact.sha256.slice(0, 12)}…</div>
      <audio src={artifact.url} preload="metadata" controls={false} data-qid="shared-chat:audio:media" />
    </section>
  )
}

export default AudioArtifact
