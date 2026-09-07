// Mirror of pitchdeck.ui_deck_bundle.v1 (src/pitchdeck/ui_emitter.py).

export interface UiClaimBadge {
  id: string
  status: 'candidate' | 'approved' | 'qualified' | 'rejected' | string
  risk: string
  kind: string
  text: string
  required_qualifier?: string
  evidence_spans?: { source_id: string; text: string; section?: string }[]
}

export interface UiAsset {
  id: string
  kind: string
  status: string
  alt_text: string
  file?: string
  missing: boolean
}

export interface UiDiagram {
  nodes: { id: string; label: string; sublabel?: string | null; bbox: { x: number; y: number; w: number; h: number } }[]
  edges: { id: string; source: string; target: string; label?: string | null; line_style?: string; arrowhead?: boolean }[]
}

export interface UiElement {
  children?: UiElement[]
  shape?: { preset: string; fill_role?: string; stroke?: { width_pt: number } }
  rotation_deg?: number
  fragment_index?: number | null
  kind?: string
  role?: string
  diagram?: UiDiagram
  crop?: { x: number; y: number; w: number; h: number }
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

export interface AnimationEffect {
  id: string
  targets: string[]
  effect: string
  phase: 'entrance' | 'exit' | 'emphasis' | 'motion'
  direction: string
  start: 'on-click' | 'with-previous' | 'after-previous'
  duration_ms: number
  delay_ms: number
  amount?: number
  color?: string
  dx?: number
  dy?: number
}

export interface UiSlide {
  animations?: AnimationEffect[]
  reveal_order?: string[]
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
  theme_tokens: import('./components/ThemePicker').ThemeTokens
  slides: UiSlide[]
  claim_summary: Record<string, number>
  validation_readiness: string
  validation_gaps: string[]
  seam_validation: { kind: string; status: 'PASS' }
}

export const CANVAS_WIDTH = 1920
export const CANVAS_HEIGHT = 1080
