export type Speaker = "graham" | "interviewer" | "unknown";
export type TranscriptKind = "interim" | "stabilized" | "final";
export type SessionStatus = "idle" | "armed" | "listening" | "paused" | "stopped";
export type RetrievalLane = "memory" | "code" | "ripgrep" | "ask" | "brave" | "dogpile";
export type LaneState = "idle" | "running" | "ok" | "degraded" | "disabled" | "error";
export type Freshness = "current" | "stale" | "unknown" | "external";
export type CardStatus = "supported" | "insufficient";

export interface TranscriptEvent {
  schema: "live_evidence.transcript_event.v1";
  event_id: string;
  created_at: string;
  speaker: Speaker;
  kind: TranscriptKind;
  source: "microphone" | "pipewire" | "demo" | "api";
  text: string;
  sequence?: number | null;
  start_ms?: number | null;
  end_ms?: number | null;
}

export interface EvidenceSource {
  schema: "live_evidence.evidence_source.v1";
  source_id: string;
  lane: RetrievalLane;
  label: string;
  excerpt: string;
  score: number;
  freshness: Freshness;
  repository?: string | null;
  branch?: string | null;
  commit?: string | null;
  path?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  url?: string | null;
  metadata: Record<string, unknown>;
}

export interface ClarificationItem {
  id: string;
  question: string;
  why_it_matters?: string | null;
  default_assumption?: string | null;
  blocking: boolean;
  answer?: string | null;
  answer_source_event_ids: string[];
}

export interface SolutionDeckPoint {
  title: string;
  trigger: string;
}

export interface EvidenceCard {
  schema: "live_evidence.evidence_card.v1";
  card_id: string;
  created_at: string;
  query: string;
  thread: string;
  question?: string | null;
  answer?: string | null;
  evidence?: string | null;
  talking_point: string;
  proof: string;
  qualifier: string;
  confidence: number;
  status: CardStatus;
  sources: EvidenceSource[];
  solution_deck?: SolutionDeckPoint[];
  question_id?: string | null;
  question_revision?: number;
  parent_question_id?: string | null;
  review_verdict?: "ok" | "weak" | null;
  review_reasons?: string[];
  amendment_text?: string | null;
  amendment_complete?: boolean;
  policy_digest?: string | null;
  frame_refs?: string[];
  lanes: RetrievalLane[];
  clarifications: ClarificationItem[];
  pinned: boolean;
  dismissed: boolean;
}

export interface LaneActivity {
  lane: RetrievalLane;
  state: LaneState;
  detail: string;
  latency_ms?: number | null;
  result_count: number;
  updated_at: string;
}

export type SessionPurpose =
  | "meeting"
  | "rehearsal"
  | "formal_assessment"
  | "interviewer_assist"
  | "post_interview_review";
export type ActorRole = "participant" | "candidate" | "interviewer" | "reviewer";

export interface CapabilityPolicy {
  capture_audio: boolean;
  retain_transcript: boolean;
  retrieve_local_evidence: boolean;
  external_search: boolean;
  candidate_answer_generation: boolean;
  interviewer_followup_suggestions: boolean;
  debugger_invocation: boolean;
  repository_mutation: boolean;
  voice_output: boolean;
}

export interface SessionInfo {
  session_id: string;
  status: SessionStatus;
  started_at?: string | null;
  stopped_at?: string | null;
  consent_confirmed: boolean;
  profile_name: string;
  purpose: SessionPurpose;
  actor_role: ActorRole;
  policy: CapabilityPolicy;
  policy_version: number;
  policy_digest: string;
  practice_only: boolean;
}

export interface AppSnapshot {
  schema: "live_evidence.app_snapshot.v1";
  session: SessionInfo;
  current_thread: string;
  transcript: TranscriptEvent[];
  cards: EvidenceCard[];
  lanes: LaneActivity[];
  external_search_enabled: boolean;
  listener?: { device: string; resolve_reason: string; mode: string; level?: string } | null;
  updated_at: string;
}

export interface ActionDefinition {
  element_id: string;
  app: string;
  action: string;
  label: string;
  description: string;
  params?: Record<string, unknown>;
  tags?: string[];
}
