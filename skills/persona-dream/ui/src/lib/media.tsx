/**
 * media helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { MediaLockFrame, StoryboardConsumerProjection } from '../types'
import { dreamAssetUrl } from './asset'
import { firstString, payloadArray, payloadObject } from './text'

export function mediaLockStatusLabel(status: string): string {
  return status.startsWith('ACCEPTED_') ? 'ACCEPTED' : status
}

export function mediaLockGroupTimeRange(frames: MediaLockFrame[]): string {
  const first = frames[0]?.timeLabel ?? 'n/a'
  const last = frames[frames.length - 1]?.timeLabel ?? first
  return first === last ? first : `${first} - ${last}`
}

export function mediaLockFrameGroups(frames: MediaLockFrame[]): Array<{ panelId: string; frames: MediaLockFrame[] }> {
  const groups = new Map<string, MediaLockFrame[]>()
  for (const frame of frames) {
    const group = groups.get(frame.panelId) ?? []
    group.push(frame)
    groups.set(frame.panelId, group)
  }
  return Array.from(groups.entries()).map(([panelId, groupFrames]) => ({
    panelId,
    frames: groupFrames,
  }))
}

export function mediaLockFramesFromPacket(packet: unknown, projection?: StoryboardConsumerProjection): MediaLockFrame[] {
  const root = payloadObject(packet)
  const panels = payloadArray(root?.panels)
  const frames: MediaLockFrame[] = []
  for (const panel of panels) {
    const panelId = firstString(panel.panel_id, panel.id) ?? `panel_${frames.length + 1}`
    const projectedPanel = projection?.panels.find((candidate) => candidate.panelId === panelId)
    const timeRange = payloadObject(panel.time_range)
    for (const role of ['start_frame', 'end_frame']) {
      const frameWrapper = payloadObject(panel[role])
      const acceptedFrame = payloadObject(frameWrapper?.accepted_frame) ?? frameWrapper
      const projectedFrame = role === 'start_frame' ? projectedPanel?.startFrame : projectedPanel?.endFrame
      if (!projectedFrame?.url) continue
      const identityReview = payloadObject(acceptedFrame?.identity_continuity_review)
      const timeValue = role === 'start_frame' ? timeRange?.start_s : timeRange?.end_s
      frames.push({
        id: `${panelId}.${role}`,
        panelId,
        role,
        path: projectedFrame.artifactId,
        url: projectedFrame.url,
        sha256: projectedFrame.sha256,
        status: firstString(acceptedFrame?.status) ?? 'ACCEPTED_FRAME',
        identityStatus: firstString(identityReview?.status) ?? 'UNKNOWN',
        acceptedAt: firstString(acceptedFrame?.accepted_at) ?? '',
        timeLabel: typeof timeValue === 'number' ? `${timeValue.toFixed(1)}s` : 'n/a',
      })
    }
  }
  return frames
}

export function graphMediaSourceFromDocument(doc?: Record<string, unknown> | null): string | undefined {
  const candidates = [doc?.source_path, doc?.url, doc?.asset_url, doc?.public_url, doc?.path, doc?.poster_path, doc?.keyframe_path, doc?.thumbnail_path, doc?.thumbnail_url]
  const value = candidates.find((candidate) => typeof candidate === 'string' && /\.(png|jpe?g|webp|gif|mp4|mov|wav|mp3)$/i.test(candidate))
  return typeof value === 'string' ? dreamAssetUrl(value) : undefined
}
