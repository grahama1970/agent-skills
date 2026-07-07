export type Team = "arena" | "red" | "blue" | "judge" | "scoreboard";
export type ReceiptStatus = "PASS" | "FAIL" | "BLOCKED" | string;

export interface BattleRunReceipt {
  schema: "battle.arena_tau_public_only_run_receipt.v1";
  battle_id: string;
  run_id: string;
  status: ReceiptStatus;
  verdict: string;
  mocked: boolean;
  live: string;
  execution_scope: string;
  created_at: string;
  upstream_arena_status: ReceiptStatus;
  artifacts: Record<string, string>;
  claims: {
    proves: string[];
    does_not_prove: string[];
  };
}

export interface BattleScoreboard {
  schema: "battle.arena_tau_public_only_scoreboard.v1";
  battle_id: string;
  run_id: string;
  scenario_id: string;
  status: ReceiptStatus;
  verdict: string;
  mode: string;
  entry_point: string;
  red_score: number;
  blue_score: number;
  judge_status: ReceiptStatus;
  tau_manifest_status: ReceiptStatus;
  visibility_status: ReceiptStatus;
  per_vulnerability: VulnerabilityOutcome[];
  non_claims: string[];
}

export interface VulnerabilityOutcome {
  id: string;
  difficulty: string;
  weight: number;
  outcome: string;
  red_exploit_replayed: boolean;
  blue_patch_replayed: boolean;
}

export interface VisibilityValidation {
  schema: "battle.arena_tau_public_only_visibility_validation.v1";
  status: ReceiptStatus;
  mocked: boolean;
  live: boolean;
  private_input_leaks: string[];
  inspected_artifacts: string[];
  proves: string[];
  team_count: number;
}

export interface JudgeReceipt {
  schema: "battle.arena_tau_public_only_judge_receipt.v1";
  status: ReceiptStatus;
  verdict: string;
  exploit_confirmed_before_patch: boolean;
  exploit_blocked_after_patch: boolean;
  functionality_preserved: boolean;
  red_artifact: string;
  blue_artifact: string;
  commands_run: JudgeCommand[];
}

export interface JudgeCommand {
  command: string[];
  exit_code: number;
  stdout_path: string;
  stderr_path: string;
}

export interface TauManifest {
  schema: "tau.battle_live_handoff_proof.v1";
  battle_id: string;
  run_id: string;
  scenario_id: string;
  status: ReceiptStatus;
  mocked: boolean;
  live: boolean;
  model: string;
  surface: string;
  scheduling: {
    mode: string;
    team_count: number;
    handoff_count: number;
    completion_order: Array<{
      team: "red" | "blue";
      persona: string;
      completed_at_seconds: number;
    }>;
  };
}

export interface TauSubagentReceipt {
  schema: "tau.subagent_receipt.v1";
  context: {
    battle: {
      battle_id: string;
      scenario_id: string;
      team: "red" | "blue";
      persona: string;
    };
  };
  result: {
    status: ReceiptStatus;
    live: boolean;
    mocked: boolean;
    summary: string;
    surface: string;
    materialized_artifact: {
      status: ReceiptStatus;
      artifact_type: string;
      path: string;
      parsed_keys: string[];
    };
  };
  evidence: string[];
  next: {
    subagent: string;
    reason: string;
  };
}

export interface ArenaScenario {
  schema: "battle.arena_scenario.v1";
  battle_id: string;
  run_id: string;
  scenario_id: string;
  scenario_kind: string;
  title: string;
  public_entrypoint: string;
  entry_point_type: string;
  target_language: string;
  difficulty: string;
  stop_condition: string;
  public_contract: {
    method: string;
    input: string;
    visible_behavior: string;
  };
}

export interface HiddenLedger {
  schema: "battle.hidden_vulnerability_ledger.v1";
  vulnerabilities: Array<{
    id: string;
    entry_point: string;
    difficulty: string;
    weight: number;
    status: string;
  }>;
}

export interface BattleGraphNode {
  id: string;
  label: string;
  group: Team;
  status: ReceiptStatus;
  detailKey: DetailKey;
  x?: number;
  y?: number;
}

export interface BattleGraphLink {
  id: string;
  source: string;
  target: string;
  label: string;
  value: number;
}

export type DetailKey =
  | "run"
  | "arena"
  | "visibility"
  | "red"
  | "blue"
  | "judge"
  | "scoreboard"
  | "tau";

export interface LoadedBattleArtifacts {
  baseUrl: string;
  run: BattleRunReceipt;
  scoreboard: BattleScoreboard;
  visibility: VisibilityValidation;
  judge: JudgeReceipt;
  tau: TauManifest;
  red: TauSubagentReceipt;
  blue: TauSubagentReceipt;
  scenario: ArenaScenario;
  ledger: HiddenLedger;
}
