export type RouteStatus = 'MATCHED' | 'AMBIGUOUS' | 'NO_MATCH'

export interface CockpitState {
  schema: 'explain_project.cockpit_state.v1'
  revision: number
  route: { status: RouteStatus; matched_feature?: string | null; candidates?: string[] } | null
  selection: { feature_id: string; step_index: number; step_count: number } | null
  teleprompter: { revision: number; title?: string | null; bullets: string[]; proof_boundary?: string | null; confidence?: 'high' | 'medium' | 'low' | null; verification: string }
  source: { revision: number; location?: { file: string; start_line: number; end_line: number; symbol?: string | null } | null; explanation?: string | null }
  debugger: { revision: number; target?: { file: string; line: number; locals: string[]; watches: string[]; proves: string } | null; status: string }
  diagram: { revision: number; rendered_svg_path?: string | null; active_node_ids: string[]; verified_binding: boolean }
}

export interface ExplainerSummary {
  feature_id: string
  title: string
  question_family: string
  question: string
  steps: number
}
