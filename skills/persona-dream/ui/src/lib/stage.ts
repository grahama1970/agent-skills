/**
 * stage helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { DreamStage } from '../types'
import { statusTone } from './status'

export function requiredStageArtifact(stage: DreamStage | undefined, artifactId: string) {
  return stage?.requiredArtifacts?.[artifactId]
}

export function createMissingStage(id: string, label: string): DreamStage {
  return {
    id,
    title: label,
    status: 'MISSING',
    summary: `No ${label} phase evidence was found in the backend run artifacts.`,
    failureOrGap: `Required preflight evidence is missing for the ${label} phase.`,
    artifacts: [],
    images: [],
  }
}

export function isStagePassed(stage: DreamStage): boolean {
  return statusTone(effectiveStageStatus(stage)) === 'pass'
}

export function stageMissingMessage(stage: DreamStage): string {
  if (isStagePassed(stage)) return 'Accepted evidence is present for this phase.'
  if (stage.id === '07') {
    if (/PANEL_ASSETS/i.test(stage.status)) {
      return stage.failureOrGap || 'Storyboard references are attached. Remaining blocker: accepted storyboard panel images/start-end frames are not present yet.'
    }
    if (/REFERENCE_GAPS/i.test(stage.status)) {
      return 'Storyboard packet is blocked: missing prop/environment references required by Phase 04 contact-sheet evidence.'
    }
    return stage.failureOrGap || 'Storyboard packet needs accepted storyboard panels and reviewer evidence before provider handoff.'
  }
  return stage.failureOrGap || 'Required preflight evidence was not found for this phase.'
}

export function effectiveStageStatus(stage: DreamStage): string {
  return stage.status
}

export function stageArtifactSummary(stage: DreamStage | undefined): Array<{ label: string; path: string; kind: string }> {
  return (stage?.artifacts ?? []).map((artifact) => ({
    label: artifact.label,
    path: artifact.path,
    kind: artifact.kind,
  }))
}

export function stageImageSummary(stage: DreamStage | undefined): Array<{ label: string; path: string; url: string }> {
  return (stage?.images ?? []).map((image) => ({
    label: image.label,
    path: image.path,
    url: image.url,
  }))
}
