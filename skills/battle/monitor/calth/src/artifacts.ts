import type { CalthMonitorIndex, CalthScoreboard } from "./types";

export interface LoadedCalthArtifacts {
  baseUrl: string;
  monitorIndex: CalthMonitorIndex;
  scoreboard: CalthScoreboard;
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

function assertMonitorIndex(value: CalthMonitorIndex): void {
  if (value.schema !== "battle.monitor_index.v1") {
    throw new Error(`Invalid monitor-index schema: ${String(value.schema)}`);
  }
  if (!value.scoreboard) {
    throw new Error("monitor-index missing scoreboard path");
  }
  if (!Array.isArray(value.players) || value.players.length !== 3) {
    throw new Error("monitor-index must contain Red, Blue, and Judge players");
  }
}

function assertScoreboard(value: CalthScoreboard): void {
  if (value.schema !== "battle.scoreboard.v1") {
    throw new Error(`Invalid scoreboard schema: ${String(value.schema)}`);
  }
  if (!value.verdict || !value.status) {
    throw new Error("scoreboard missing verdict or status");
  }
}

export async function loadCalthArtifacts(): Promise<LoadedCalthArtifacts> {
  const baseUrl = artifactBaseUrl();
  const monitorIndex = await fetchJson<CalthMonitorIndex>(baseUrl, "monitor-index.json");
  assertMonitorIndex(monitorIndex);

  const scoreboard = await fetchJson<CalthScoreboard>(baseUrl, monitorIndex.scoreboard);
  assertScoreboard(scoreboard);

  const receipts: Record<string, unknown> = {};
  for (const player of monitorIndex.players) {
    receipts[player.team] = await fetchJson<unknown>(baseUrl, player.receipt);
  }

  return {
    baseUrl,
    monitorIndex,
    scoreboard,
    receipts
  };
}
