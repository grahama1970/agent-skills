import type {
  ArenaScenario,
  BattleRunReceipt,
  BattleScoreboard,
  HiddenLedger,
  JudgeReceipt,
  LoadedBattleArtifacts,
  TauManifest,
  TauSubagentReceipt,
  VisibilityValidation
} from "./types";

function artifactBaseUrl(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("artifactBase") ?? "/artifacts/arena-tau-public-only-002";
}

async function fetchJson<T>(baseUrl: string, relativePath: string): Promise<T> {
  const url = `${baseUrl.replace(/\/$/, "")}/${relativePath.replace(/^\//, "")}`;
  const response = await fetch(url, { cache: "no-store" });

  if (!response.ok) {
    throw new Error(`Missing or unreadable Battle artifact: ${url} (${response.status})`);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new Error(`Invalid JSON Battle artifact: ${url}`);
  }
}

function requireSchema(value: { schema?: string }, expected: string, path: string): void {
  if (value.schema !== expected) {
    throw new Error(`Invalid schema for ${path}: ${String(value.schema)}`);
  }
}

export async function loadBattleArtifacts(): Promise<LoadedBattleArtifacts> {
  const baseUrl = artifactBaseUrl();
  const run = await fetchJson<BattleRunReceipt>(baseUrl, "run-receipt.json");
  requireSchema(run, "battle.arena_tau_public_only_run_receipt.v1", "run-receipt.json");

  const scoreboard = await fetchJson<BattleScoreboard>(baseUrl, run.artifacts.scoreboard);
  requireSchema(scoreboard, "battle.arena_tau_public_only_scoreboard.v1", run.artifacts.scoreboard);

  const visibility = await fetchJson<VisibilityValidation>(
    baseUrl,
    run.artifacts.visibility_validation
  );
  requireSchema(
    visibility,
    "battle.arena_tau_public_only_visibility_validation.v1",
    run.artifacts.visibility_validation
  );

  const judge = await fetchJson<JudgeReceipt>(baseUrl, run.artifacts.judge_receipt);
  requireSchema(judge, "battle.arena_tau_public_only_judge_receipt.v1", run.artifacts.judge_receipt);

  const tau = await fetchJson<TauManifest>(baseUrl, run.artifacts.tau_manifest);
  requireSchema(tau, "tau.battle_live_handoff_proof.v1", run.artifacts.tau_manifest);

  const red = await fetchJson<TauSubagentReceipt>(baseUrl, run.artifacts.red_tau_subagent_receipt);
  requireSchema(red, "tau.subagent_receipt.v1", run.artifacts.red_tau_subagent_receipt);

  const blue = await fetchJson<TauSubagentReceipt>(baseUrl, run.artifacts.blue_tau_subagent_receipt);
  requireSchema(blue, "tau.subagent_receipt.v1", run.artifacts.blue_tau_subagent_receipt);

  const scenario = await fetchJson<ArenaScenario>(baseUrl, "arena/scenario.json");
  requireSchema(scenario, "battle.arena_scenario.v1", "arena/scenario.json");

  const ledger = await fetchJson<HiddenLedger>(baseUrl, run.artifacts.arena_private_ledger);
  requireSchema(
    ledger,
    "battle.hidden_vulnerability_ledger.v1",
    run.artifacts.arena_private_ledger
  );

  return {
    baseUrl,
    run,
    scoreboard,
    visibility,
    judge,
    tau,
    red,
    blue,
    scenario,
    ledger
  };
}
