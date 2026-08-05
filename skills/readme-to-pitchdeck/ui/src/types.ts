// Mirror of readme_to_pitchdeck.ui_deck_bundle.v1 (src/readme_to_pitchdeck/ui_emitter.py).

export interface UiClaimBadge {
  id: string
  status: 'candidate' | 'approved' | 'qualified' | 'rejected' | string
  risk: string
  kind: string
  text: string
  required_qualifier?: string
}

export interface UiAsset {
  id: string
  kind: string
  status: string
  alt_text: string
  file?: string
  missing: boolean
}

export interface UiElement {
  id: string
  type: 'text' | 'asset' | string
  x: number
  y: number
  w: number
  h: number
  text?: string
  size_pt: number
  bold: boolean
  color?: string
  align: string
  asset?: UiAsset
  entrance: 'none' | 'fade' | 'rise' | 'zoom' | string
  entrance_delay_ms: number
}

export interface UiVisual {
  type: 'none' | 'image' | 'screenshot' | 'native_diagram' | 'cards' | string
  position: 'left' | 'right' | 'full' | string
  asset?: UiAsset
  items: string[]
  callouts: string[]
  caption?: string
  source?: string
}

export interface UiSlide {
  id: string
  order: number
  layout: string
  role: string
  title: string
  message: string
  body: string[]
  visual: UiVisual
  elements: UiElement[]
  hidden: boolean
  transition: 'none' | 'fade' | 'slide' | 'slide_up' | 'zoom' | 'flip' | 'wipe' | string
  transition_duration_ms: number
  reveal: 'none' | 'stagger_up' | 'stagger_fade' | string
  claims: UiClaimBadge[]
  source_ids: string[]
  notes: string
  footer?: string
}

export interface UiDeckBundle {
  schema: string
  revision: number
  deck_id: string
  title: string
  subtitle?: string
  audience: string
  visibility: 'public' | 'private' | string
  theme: string
  theme_tokens: { accent: string; heading_font: string; body_font: string }
  slides: UiSlide[]
  claim_summary: Record<string, number>
  validation_readiness: string
  validation_gaps: string[]
  seam_validation: { kind: string; status: 'PASS' }
}

export const CANVAS_WIDTH = 1920
export const CANVAS_HEIGHT = 1080
