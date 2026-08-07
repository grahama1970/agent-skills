/**
 * contact helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { ContactSheetDecision, StoryMatrixRow } from '../types'

export const contactSheetDecisionForStoryRow = (row: Pick<StoryMatrixRow, 'name' | 'objects' | 'dynamics' | 'note'>): ContactSheetDecision => {
  const name = row.name.toLowerCase()
  const text = `${row.name} ${row.objects} ${row.dynamics} ${row.note}`.toLowerCase()
  if (/\b(shortboard|surfboard|board|rashguard|phone)\b/.test(name)) {
    return {
      required: true,
      kind: 'prop',
      status: 'missing',
      send_to_kling: true,
      priority: 'conditional',
      rationale: 'Visually specific props or wardrobe affect staging; include a reference sheet when visible in the panel.',
    }
  }
  if (/\b(kahalu|kona|bay|coast|reef|beach|lineup|bed|bedroom|garage|swell)\b/.test(name)) {
    return {
      required: true,
      kind: 'environment',
      status: 'missing',
      send_to_kling: true,
      priority: 'recommended',
      rationale: 'Stable scene geometry should use a compact environment reference when it anchors the panel.',
    }
  }
  if (/^(embry|embry lawson|kai|kai akana)$/.test(name.trim())) {
    return {
      required: true,
      kind: 'character',
      status: 'existing_or_required',
      send_to_kling: true,
      priority: 'required',
      rationale: 'Character identity continuity must be locked before video provider generation.',
    }
  }
  if (/\b(shortboard|surfboard|board|rashguard|phone)\b/.test(text)) {
    return {
      required: true,
      kind: 'prop',
      status: 'missing',
      send_to_kling: true,
      priority: 'conditional',
      rationale: 'Visually specific props or wardrobe affect staging; include a reference sheet when visible in the panel.',
    }
  }
  if (/\b(kahalu|kona|bay|coast|reef|beach|lineup|bed|bedroom|garage)\b/.test(text)) {
    return {
      required: true,
      kind: 'environment',
      status: 'missing',
      send_to_kling: true,
      priority: 'recommended',
      rationale: 'Stable scene geometry should use a compact environment reference when it anchors the panel.',
    }
  }
  return {
    required: false,
    kind: 'prompt_only',
    status: 'not_needed',
    send_to_kling: false,
    priority: 'prompt_only',
    rationale: 'Abstract forces such as heat, humidity, glare, etiquette, or fatigue should be described in the prompt, not as contact sheets.',
  }
}
