/**
 * idea helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import type { HumanIdeaProjection } from '../types'

export function persistedHumanIdea(projection?: HumanIdeaProjection): string {
  return projection?.source === 'explicit_human' ? projection.text.trim() : ''
}
