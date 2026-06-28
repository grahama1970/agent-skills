import type { BattleMonitorIndex, BattleScoreboard } from "./types";

export interface LoadedBattleArtifacts {
  baseUrl: string;
  monitorIndex: BattleMonitorIndex;
  scoreboard: BattleScoreboard;
  receipts: Record<string, unknown>;
}

function artifactBaseUrl(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("artifactBase") ?? "/artifacts/battle-001";
}

async function fetchJson<T>(baseUrl: string, relativePath: string): Promise<T> {
  const url = `${baseUrl.replace(/\/$/, "")}/${relativePath.replace(/^\//, "")}`;
  const response = await fetch(url, { cache: "no-store" });

  if (!response.ok) {
    throw new Error(`Missing or unreadable Battle artifact: ${url} (${response.status})`);
  }

  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch (error) {
    throw new Error(`Missing or unreadable Battle artifact: ${url}`);
  }
}

function assertMonitorIndex(value: BattleMonitorIndex): void {
  if (value.schema !== "battle.monitor_index.v1") {
    throw new Error(`Invalid monitor-index schema: ${String(value.schema)}`);
  }
  if (!value.scoreboard) {
    throw new Error("monitor-index missing scoreboard path");
  }
  if (!Array.isArray(value.players) || value.players.length < 3) {
    throw new Error("monitor-index must contain at least Red, Blue, and Judge players");
  }
  const teams = new Set(value.players.map((player) => player.team));
  for (const team of ["red", "blue", "judge"] as const) {
    if (!teams.has(team)) {
      throw new Error(`monitor-index missing ${team} player`);
    }
  }
}

function assertScoreboard(value: BattleScoreboard): void {
  if (value.schema !== "battle.scoreboard.v1") {
    throw new Error(`Invalid scoreboard schema: ${String(value.schema)}`);
  }
  if (!value.verdict || !value.status) {
    throw new Error("scoreboard missing verdict or status");
  }
}

export async function loadBattleArtifacts(): Promise<LoadedBattleArtifacts> {
  const baseUrl = artifactBaseUrl();
  const monitorIndex = await fetchJson<BattleMonitorIndex>(baseUrl, "monitor-index.json");
  assertMonitorIndex(monitorIndex);

  const scoreboard = await fetchJson<BattleScoreboard>(baseUrl, monitorIndex.scoreboard);
  assertScoreboard(scoreboard);

  const receiptPaths = new Map<string, string>();
  for (const player of monitorIndex.players) {
    receiptPaths.set(player.team, player.receipt);
  }
  for (const [name, path] of Object.entries(scoreboard.receipts ?? {})) {
    if (path) {
      receiptPaths.set(name, path);
    }
  }

  const receiptEntries = await Promise.all(
    [...receiptPaths.entries()].map(async ([name, path]) => {
      return [name, await fetchJson<unknown>(baseUrl, path)] as const;
    })
  );
  const receipts = Object.fromEntries(receiptEntries);

  return {
    baseUrl,
    monitorIndex,
    scoreboard,
    receipts
  };
}
