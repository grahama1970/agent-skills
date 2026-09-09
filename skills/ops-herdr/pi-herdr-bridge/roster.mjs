// Merged session roster: pi-intercom broker sessions + Herdr agent panes.
// Herdr side is read via `herdr agent list` (verified live: returns
// {agents:[{agent, agent_session:{kind,value}, pane_id, agent_status, cwd, ...}]}).
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// Build a { tab_id -> label } map from `herdr tab list` output. Tab labels
// (e.g. "devops") are the human-facing names of tabs and are NOT present in
// `herdr agent list`; only the per-pane terminal title is. Joining on tab_id
// makes a tab like "devops" addressable even when its pane title is "π - x".
export function normalizeTabLabels(tabListResult) {
  const tabs = tabListResult?.result?.tabs ?? tabListResult?.tabs ?? [];
  const map = new Map();
  for (const t of tabs) {
    if (t?.tab_id && t?.label) map.set(t.tab_id, t.label);
  }
  return map;
}

export function normalizeHerdrAgents(agentListResult, tabLabels = new Map()) {
  const agents = agentListResult?.result?.agents ?? agentListResult?.agents ?? [];
  return agents.map((a) => ({
    source: "herdr",
    provider: a.agent,
    name: a.terminal_title_stripped || null,
    tabLabel: (a.tab_id && tabLabels.get(a.tab_id)) || null,
    tabId: a.tab_id ?? null,
    paneId: a.pane_id,
    workspaceId: a.workspace_id,
    terminalId: a.terminal_id,
    cwd: a.cwd,
    status: a.agent_status,
    sessionRef: a.agent_session
      ? { kind: a.agent_session.kind, value: a.agent_session.value, refSource: a.agent_session.source }
      : null,
  }));
}

export function normalizeBrokerSessions(sessions, selfSessionId = null) {
  return (sessions ?? [])
    .filter((s) => s.id !== selfSessionId)
    .map((s) => ({
      source: "intercom",
      provider: "pi",
      name: s.name ?? null,
      paneId: null,
      workspaceId: null,
      terminalId: null,
      cwd: s.cwd,
      status: s.status ?? null,
      sessionRef: { kind: "id", value: s.id, refSource: "pi-intercom" },
    }));
}

// Broker-registered Pi sessions and Herdr-detected pi panes describe the same
// underlying processes differently (intercom id vs jsonl path); both rows are
// kept, with intercom preferred for routing (structured triggerTurn delivery).
export function mergeRoster(brokerEntries, herdrEntries) {
  return [...brokerEntries, ...herdrEntries];
}

export async function herdrRoster({ herdrBin = "herdr" } = {}) {
  const [agentOut, tabOut] = await Promise.all([
    execFileAsync(herdrBin, ["agent", "list"], { maxBuffer: 16 * 1024 * 1024 }),
    // Tab labels are best-effort: a missing/failed tab list must not drop the
    // whole roster, only the tabLabel enrichment.
    execFileAsync(herdrBin, ["tab", "list"], { maxBuffer: 16 * 1024 * 1024 }).catch(() => ({ stdout: "{}" })),
  ]);
  let tabLabels = new Map();
  try {
    tabLabels = normalizeTabLabels(JSON.parse(tabOut.stdout));
  } catch {
    tabLabels = new Map();
  }
  return normalizeHerdrAgents(JSON.parse(agentOut.stdout), tabLabels);
}

// Resolve a target by (in priority order): exact intercom name, exact herdr
// terminal title, exact herdr tab label, session-ref value, pane id. Fails
// closed on ambiguity.
export function resolveTarget(roster, query) {
  const q = query.trim();
  const lanes = [
    (e) => e.source === "intercom" && e.name === q,
    (e) => e.source === "herdr" && e.name === q,
    (e) => e.source === "herdr" && e.tabLabel === q,
    (e) => e.sessionRef?.value === q,
    (e) => e.paneId === q,
  ];
  for (const match of lanes) {
    const hits = roster.filter(match);
    if (hits.length === 1) return { entry: hits[0] };
    if (hits.length > 1) {
      return { error: `ambiguous target "${q}": ${hits.length} matches`, matches: hits };
    }
  }
  return { error: `no session matches "${q}"`, matches: [] };
}
