/**
 * Composed base style vocabulary.
 */
import type { CSSProperties } from 'react'
import { baseGateStyles } from './base-gate'
import { baseMediaStyles } from './base-media'
import { baseStageStyles } from './base-stage'
import { baseCommonStyles } from './base-common'

export const styles: Record<string, CSSProperties> = {
  ...baseGateStyles,
  ...baseMediaStyles,
  ...baseStageStyles,
  ...baseCommonStyles,
}
