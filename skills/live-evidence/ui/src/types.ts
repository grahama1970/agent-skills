export type Speaker = "graham" | "interviewer" | "unknown";
export type TranscriptKind = "interim" | "stabilized" | "final";
export type SessionStatus = "idle" | "listening" | "paused" | "stopped";
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

export interface EvidenceCard {
  schema: "live_evidence.evidence_card.v1";
  card_id: string;
  created_at: string;
  query: string;
  thread: string;
  talking_point: string;
  proof: string;
  qualifier: string;
  confidence: number;
  status: CardStatus;
  sources: EvidenceSource[];
  lanes: RetrievalLane[];
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

export interface SessionInfo {
  session_id: string;
  status: SessionStatus;
  started_at?: string | null;
  stopped_at?: string | null;
  consent_confirmed: boolean;
  profile_name: string;
}

export interface AppSnapshot {
  schema: "live_evidence.app_snapshot.v1";
  session: SessionInfo;
  current_thread: string;
  transcript: TranscriptEvent[];
  cards: EvidenceCard[];
  lanes: LaneActivity[];
  external_search_enabled: boolean;
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
