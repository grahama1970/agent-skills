export type GateStatus =
  | 'PASS'
  | 'FAIL'
  | 'BLOCKED'
  | 'NEEDS_ATTENTION'
  | 'DRY_RUN'
  | 'SKIPPED'
  | 'UNKNOWN';

export interface TriageSummary {
  code: string | null;
  cause: string | null;
  next_command: string | null;
  recoverable: boolean | null;
  source: string;
}

export interface TauDagNode {
  id: string;
  label: string;
  status: string;
  agent: string | null;
}

export interface TauDagEdge {
  id: string;
  source: string;
  target: string;
}

export interface TauDagGraph {
  dag_id: string | null;
  status: string | null;
  verdict: string | null;
  nodes: TauDagNode[];
  edges: TauDagEdge[];
}

export interface TauDagLink {
  expected: boolean;
  available: boolean;
  run_dir: string | null;
  progress_path: string | null;
  stream_monitor_path: string | null;
  viewer_hint: string;
  graph: TauDagGraph | null;
}

export interface WatchdogItem {
  item_id: string;
  kind: 'ticket' | 'tick' | string;
  project_id: string | null;
  repo: string | null;
  issue_number: number | null;
  issue_url: string | null;
  action: string | null;
  status: string;
  gate_status: GateStatus;
  summary: string;
  targets: string[];
  receipt_path: string | null;
  receipt_dir: string | null;
  run_id: string | null;
  updated_at: string | null;
  stop_reason: string | null;
  triage: TriageSummary | null;
  tau_dag: TauDagLink | null;
  evidence_paths: string[];
}

export interface WatchdogSnapshot {
  schema: 'agent_skills.project_watchdog.ui_snapshot.v1';
  generated_at: string;
  source: {
    status_schema?: string;
    receipt_root?: string;
    cron_log_file?: string;
    log_file?: string;
  };
  global_state: Record<string, unknown>;
  project_count: number;
  project_ids: string[];
  lock_held: boolean;
  idle_streaks: Record<string, unknown>;
  receipt_count_reported: number | null;
  receipt_limit: number;
  counts: Record<string, number>;
  items: WatchdogItem[];
  warnings: string[];
}

export type WatchdogFilter = GateStatus | 'ALL';
