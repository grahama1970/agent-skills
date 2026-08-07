/**
 * Module-scope constants for the Dream workspace.
 *
 * Only pure data lives here -- phase vocabularies, storage keys, column
 * definitions. Anything holding JSX or a mutable cache stays with the
 * component that owns it, so importing this file can never pull in a render
 * tree or shared state.
 */
import type React from 'react'
import { BookOpen, FileText, Grid, Image, Layout, Lightbulb, Mic, Package, Play, ShieldCheck, Users } from 'lucide-react'
import type { StoryMatrixRow } from './types'

export const phase02RequiredMediaKeys = [
  'embry_media_asset__assets_surfing_embry_surfing_big_island_2024_png',
  'embry_media_asset__assets_character_sheet_montage_jpg',
  'embry_media_asset__assets_surfing_embry_barrel_wave_big_island_2024_png',
  'kai_akana_media_asset__assets_surfing_kai_surfing_big_island_2024_png',
  'kai_akana_media_asset__assets_contact_sheets_kai_akana_character_sheet_png',
  'embry_kai_media_asset__assets_surfing_embry_and_kai_looking_for_waves_big_island_2024_png',
  'embry_kai_media_asset__assets_youtube_ocean_raw_surfing_audio_2min_wav',
  'embry_kai_media_asset__assets_youtube_nazare_big_wave_drone_video_mp4',
]

export const phase02RequiredTextKeys = [
  'embry_age19_23_b01_memory_012',
  'embry_age19_23_b01_memory_029',
  'embry_age15_19_b03_memory_016',
]

export const CANONICAL_PHASES = [
  { id: '01', label: 'Idea', icon: Lightbulb, legacyIds: ['phase_01_idea_memory'] },
  { id: '02', label: 'Story', icon: BookOpen, legacyIds: ['phase_02_story_entities_json'] },
  { id: '03', label: 'Crew', icon: Users, legacyIds: ['phase_03_producer_writer_director'] },
  { id: '04', label: 'Contact Sheets', icon: Image, legacyIds: ['phase_04_contact_sheets'] },
  { id: '05', label: 'Voices', icon: Mic, legacyIds: ['phase_05_orpheus_voices'] },
  { id: '06', label: 'Script', icon: FileText, legacyIds: ['phase_06_script'] },
  { id: '07', label: 'Storyboard', icon: Layout, legacyIds: ['phase_07_storyboard'] },
  { id: '08', label: 'Media Lock', icon: Grid, legacyIds: ['phase_08_panels_environment', 'media-lock', 'panels'] },
  { id: '09', label: 'Video Provider', icon: Package, legacyIds: ['phase_09_kling_optimized_packet', 'video-provider', 'kling-packet'] },
  { id: '10', label: 'Provider Distillation', icon: ShieldCheck, legacyIds: ['phase_10_provider_contract', 'phase_10_creator_reviewer_gate'] },
  { id: '11', label: 'Provider Return', icon: Play, legacyIds: ['phase_11_kling_response'] },
] as const

export const phaseIcons: Record<string, React.ComponentType<{ size?: number }>> = {
  '01': Lightbulb,
  '02': BookOpen,
  '03': Users,
  '04': Image,
  '05': Mic,
  '06': FileText,
  '07': Layout,
  '08': Grid,
  '09': Package,
  '10': ShieldCheck,
  '11': Play,
}

export const crewGateMatchTerms = ['producer', 'script_writer', 'director', 'casting_contract', 'casting_plan', 'casting_agent']

export const crewMissingEvidenceFields = [
  'selected producer, scriptwriter, and director ids/names',
  'rationales for why each persona fits this story',
  'source story + interaction matrix coverage',
  'linked visual assets used for continuity',
  'crew prompt payload receipt path',
]

export const videoProviderFitColumns = [
  { key: 'image_to_video', label: 'I2V', title: 'Image-to-video fidelity' },
  { key: 'first_last_frame_control', label: 'Ends', title: 'First and last frame transition control' },
  { key: 'identity_reference_support', label: 'ID', title: 'Identity continuity and reference support' },
  { key: 'motion_quality', label: 'Motion', title: 'Motion quality and physics' },
  { key: 'multi_character_consistency', label: 'Chars', title: 'Multi-character consistency' },
] as const

export const DREAM_STORY_DRAFT_STORAGE_KEY = 'dream.phase02.storyDraft'

export const DREAM_STORY_STATUS_STORAGE_KEY = 'dream.phase02.storyStatus'

export const splitStoryObjects = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map(String).map((item) => item.trim()).filter(Boolean)
  return String(value ?? '')
    .replace(/;/g, ',')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export const storyRowCategory = (row: StoryMatrixRow): 'character' | 'character_object' | 'environmental_force' | 'location_social_system' => {
  const name = row.name.toLowerCase()
  if (name === 'embry' || name === 'kai') return 'character'
  if (name.includes('board') || name.includes('phone') || name.includes('rashguard')) return 'character_object'
  if (name.includes('coast') || name.includes('bay') || name.includes('lineup') || name.includes('etiquette')) return 'location_social_system'
  return 'environmental_force'
}

export const DREAM_SCRIPT_DRAFT_STORAGE_KEY = 'dream.phase06.scriptDraft'

export const DREAM_SCRIPT_STATUS_STORAGE_KEY = 'dream.phase06.scriptStatus'

export const textEncoder = new TextEncoder()

export const storyboardReviewerChecklist = {
  schema: 'persona_dream.storyboard_panel_reviewer_checklist.v1',
  hard_acceptance_rule: 'accepted=true only when every required identity is visible, reference-matched, and scene-appropriate; composition-only success cannot pass.',
  identity_checks: {
    required_per_identity_fields: [
      'required',
      'visible',
      'matches_reference',
      'confidence',
      'failure_code',
      'visible_evidence',
    ],
    blocking_failure_codes: [
      'embry_not_visible',
      'kai_not_visible',
      'embry_identity_mismatch',
      'kai_identity_mismatch',
      'generic_surfer_substitution',
      'wrong_gender_or_age_presentation',
      'identity_too_distant_or_occluded',
    ],
  },
  composition_checks: [
    'is_storyboard_frame',
    'not_contact_sheet',
    'not_collage',
    'not_reference_board',
    'setting_matches',
    'aspect_ratio_matches',
  ],
  rule_priority: [
    'identity failures outrank aspect/layout success',
    'contact sheets are reference inputs only, never valid storyboard frame outputs',
    'failed panels must return exact blocker codes and cannot be accepted as provider-ready',
  ],
}
