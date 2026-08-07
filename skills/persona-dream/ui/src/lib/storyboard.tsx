/**
 * storyboard helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'

export function panelHasAcceptedStoryboardFrames(panel: Record<string, unknown>): boolean {
  const startFrame = storyboardRecord(panel.start_frame)
  const endFrame = storyboardRecord(panel.end_frame)
  return Boolean(acceptedStoryboardFrame(startFrame) && acceptedStoryboardFrame(endFrame))
}

export function storyboardTargetPanelIds(packet: Record<string, unknown> | null): string[] {
  const generationScope = storyboardRecord(packet?.generation_scope)
  const targetPanelIds = generationScope.target_panel_ids
  if (!Array.isArray(targetPanelIds)) return []
  return targetPanelIds.map(String).filter(Boolean)
}

export function acceptedStoryboardFrame(frame: Record<string, unknown>): Record<string, unknown> | null {
  const accepted = storyboardRecord(frame.accepted_frame)
  const status = String(accepted.status ?? '')
  const path = String(accepted.path ?? accepted.image_path ?? '')
  if (!path) return null
  if (!/^ACCEPTED_(START|END)_FRAME$|^ACCEPTED_STORYBOARD_FRAME$|^PASS_PANEL_REVIEWED$/.test(status)) return null
  return accepted
}

export function storyboardRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

export function storyboardStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

export function storyboardShotCode(shot: string): string {
  const value = shot.toLowerCase()
  if (value.includes('extreme wide')) return 'EWS'
  if (value.includes('wide') || value.includes('establish')) return 'WS'
  if (value.includes('medium')) return 'MS'
  if (value.includes('close')) return 'CU'
  if (value.includes('waterline')) return 'POV'
  if (value.includes('two-character') || value.includes('two character')) return 'MWS'
  return 'SHOT'
}

export function storyboardPanelPromptText(payload: Record<string, unknown>): string {
  const prompt = storyboardRecord(payload.generation_prompt)
  const startFrame = storyboardRecord(payload.start_frame)
  const endFrame = storyboardRecord(payload.end_frame)
  const lines = [
    `Panel: ${String(payload.panel_id ?? 'unknown')}`,
    `Time range: ${JSON.stringify(payload.time_range ?? {})}`,
    '',
    'SHOT',
    String(payload.shot ?? ''),
    '',
    'ACTION',
    String(payload.action ?? ''),
    '',
    payload.dialogue ? `DIALOGUE\n${String(payload.dialogue)}\n` : '',
    'PANEL GENERATION PROMPT',
    String(prompt.panel_prompt ?? ''),
    '',
    'START FRAME PROMPT',
    String(prompt.start_frame_prompt ?? startFrame.description ?? ''),
    '',
    'END FRAME PROMPT',
    String(prompt.end_frame_prompt ?? endFrame.description ?? ''),
    '',
    'NEGATIVE PROMPT',
    String(prompt.negative_prompt ?? ''),
    '',
    'REQUIRED ENTITIES',
    storyboardStringList(payload.required_entities).join(', '),
    '',
    'COVERAGE SEED IDS',
    storyboardStringList(payload.coverage_seed_ids).join(', '),
    '',
    'REVIEWER HARD GATE',
    'Reject when Embry or Kai are required but missing, generic, wrong, occluded, too distant, or not reference-matched.',
  ]
  return lines.filter((line) => line !== '').join('\n')
}
