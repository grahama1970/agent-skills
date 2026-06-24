import type {
  ChatMessage,
  DisclosureVariant,
  StreamingStep,
  ThinkingTraceLikeStep,
  TurnBranch,
} from './memory-turn'
import { liveStatusLabelFromSteps, streamingStepsToThinkingTrace } from './memory-turn'

export type ThinkingTraceLeadingIcon = 'sparkle' | 'shield' | 'mic' | 'none'

export interface ThinkingTraceDisclosureParts {
  label: string
  title: string
  leadingIcon: ThinkingTraceLeadingIcon
  disclosureVariant: DisclosureVariant
  liveStatusLabel: string
}

export type ThinkingTraceSource = {
  message?: ChatMessage
  branch?: TurnBranch
  disclosureVariant?: DisclosureVariant
  streamingSteps?: StreamingStep[]
}

export function branchFromMessage(message?: ChatMessage): TurnBranch | undefined {
  const branch = message?.metadata?.branch
  return typeof branch === 'string' ? (branch as TurnBranch) : undefined
}

export function branchFromSteps(steps?: StreamingStep[]): TurnBranch | undefined {
  if (!steps?.length) return undefined
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const branch = steps[index]?.branch
    if (branch) return branch
  }
  return undefined
}

export function isEvidenceCaseMessage(message?: ChatMessage): boolean {
  return Boolean(
    message?.evidenceCase === true ||
      message?.skillUsed === 'create-evidence-case' ||
      message?.metadata?.branch === 'evidence-case' ||
      message?.metadata?.disclosureVariant === 'evidence-case',
  )
}

export function isEvidenceCaseStreaming(steps?: StreamingStep[]): boolean {
  return Boolean(
    steps?.some((step) => step.branch === 'evidence-case' || step.disclosureVariant === 'evidence-case'),
  )
}

export function leadingIconForBranch(
  branch?: TurnBranch,
  disclosureVariant?: DisclosureVariant,
): ThinkingTraceLeadingIcon {
  if (disclosureVariant === 'evidence-case' || branch === 'evidence-case') return 'shield'
  if (branch === 'personaplex') return 'mic'
  if (branch === 'watch') return 'sparkle'
  if (branch === 'compliance' || branch === 'aql') return 'shield'
  return 'sparkle'
}

export function thinkingTraceDisclosureParts(source: ThinkingTraceSource = {}): ThinkingTraceDisclosureParts {
  const branch = source.branch ?? branchFromSteps(source.streamingSteps) ?? branchFromMessage(source.message)
  const variant: DisclosureVariant =
    source.disclosureVariant ??
    (isEvidenceCaseMessage(source.message) || isEvidenceCaseStreaming(source.streamingSteps) ? 'evidence-case' : 'thinking')

  if (variant === 'evidence-case' || branch === 'evidence-case') {
    return {
      label: 'Show evidence case',
      title: 'Evidence case',
      leadingIcon: 'shield',
      disclosureVariant: 'evidence-case',
      liveStatusLabel: liveStatusLabelFromSteps(source.streamingSteps ?? [], 'Building evidence case…'),
    }
  }

  if (branch === 'personaplex') {
    return {
      label: 'Show thinking',
      title: 'Persona thinking',
      leadingIcon: 'mic',
      disclosureVariant: 'thinking',
      liveStatusLabel: liveStatusLabelFromSteps(source.streamingSteps ?? [], 'Show thinking'),
    }
  }

  if (branch === 'watch') {
    return {
      label: 'Show thinking',
      title: 'Watch thinking',
      leadingIcon: 'sparkle',
      disclosureVariant: 'thinking',
      liveStatusLabel: liveStatusLabelFromSteps(source.streamingSteps ?? [], 'Checking the scene memory…'),
    }
  }

  return {
    label: 'Show thinking',
    title: 'Thinking',
    leadingIcon: leadingIconForBranch(branch, variant),
    disclosureVariant: 'thinking',
    liveStatusLabel: liveStatusLabelFromSteps(source.streamingSteps ?? [], 'Thinking…'),
  }
}

export function thinkingStepsForMessage(
  message?: ChatMessage,
  liveStreamingSteps?: StreamingStep[],
): ThinkingTraceLikeStep[] {
  if (liveStreamingSteps?.length) return streamingStepsToThinkingTrace(liveStreamingSteps)
  return message?.thinkingTrace ?? message?.reasoningSteps ?? []
}

export function footerBranchLabel(branch?: TurnBranch): string | undefined {
  if (!branch) return undefined
  if (branch === 'evidence-case') return 'Evidence case'
  if (branch === 'personaplex') return 'PersonaPlex'
  if (branch === 'watch') return 'Watch'
  if (branch === 'aql') return 'AQL'
  if (branch === 'utility') return 'Utility'
  return 'Compliance'
}
