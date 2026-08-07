/**
 * Composed style vocabulary for the Dream workspace.
 *
 * `nvis` is assembled from per-domain modules rather than declared as one
 * 4,439-line literal. Consumers that only need one domain should import that
 * module directly; this barrel exists for the root while panels are extracted.
 */
import type { CSSProperties } from 'react'
import { assetStyles } from './asset'
import { commonStyles } from './common'
import { contactStyles } from './contact'
import { crewStyles } from './crew'
import { directorStyles } from './director'
import { ideaStyles } from './idea'
import { matrixStyles } from './matrix'
import { memoryStyles } from './memory'
import { pinStyles } from './pin'
import { providerStyles } from './provider'
import { researchStyles } from './research'
import { scriptStyles } from './script'
import { storyboardStyles } from './storyboard'
import { traceStyles } from './trace'
import { videoStyles } from './video'
import { voiceStyles } from './voice'

export const nvis: Record<string, CSSProperties> = {
  ...assetStyles,
  ...commonStyles,
  ...contactStyles,
  ...crewStyles,
  ...directorStyles,
  ...ideaStyles,
  ...matrixStyles,
  ...memoryStyles,
  ...pinStyles,
  ...providerStyles,
  ...researchStyles,
  ...scriptStyles,
  ...storyboardStyles,
  ...traceStyles,
  ...videoStyles,
  ...voiceStyles,
}
