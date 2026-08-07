/**
 * PhaseIcon, extracted from DreamWorkspace.tsx.
 */
import { CANONICAL_PHASES, DREAM_SCRIPT_DRAFT_STORAGE_KEY, DREAM_SCRIPT_STATUS_STORAGE_KEY, DREAM_STORY_DRAFT_STORAGE_KEY, DREAM_STORY_STATUS_STORAGE_KEY, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, phaseIcons, splitStoryObjects, storyRowCategory, storyboardReviewerChecklist, textEncoder, videoProviderFitColumns } from '../constants'
import { Wand2 } from 'lucide-react'

export function PhaseIcon({ phaseId, size = 18 }: { phaseId: string; size?: number }) {
  const Icon = phaseIcons[phaseId] ?? Wand2
  return <Icon size={size} />
}
