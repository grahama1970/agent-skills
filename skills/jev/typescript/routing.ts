/** Host-owned scheduling and Memory outcome mapping; neither executes nor approves. */
import { finite, fingerprint, keys, record, text, type Candidate } from "./runtime.ts";

export interface ModelOption {
  id: string; capabilities: string[]; qualified: boolean; authorized: boolean; available_slots: number;
  observed_at_ms: number; expires_at_ms: number; cooldown_until_ms: number;
  estimated_total_cost: number; estimated_latency_ms: number;
}
export function chooseModel(input: unknown[], options: {
  required: string[]; now_ms: number; max_cost: number; deadline_ms: number; pinned?: string;
}): string | null {
  const fields = ["id","capabilities","qualified","authorized","available_slots","observed_at_ms","expires_at_ms","cooldown_until_ms","estimated_total_cost","estimated_latency_ms"];
  const models = input.map(raw => {
    const m = record(raw); keys(m, fields); text(m.id);
    if (!Array.isArray(m.capabilities) || m.capabilities.some((v: unknown) => typeof v !== "string") || typeof m.qualified !== "boolean" || typeof m.authorized !== "boolean") throw new Error("model_shape");
    for (const k of fields.slice(4)) finite(m[k], 0, Number.MAX_SAFE_INTEGER);
    for (const k of fields.slice(4).filter(k => k !== "estimated_total_cost")) if (!Number.isInteger(m[k])) throw new Error("model_integer");
    if (m.expires_at_ms < m.observed_at_ms) throw new Error("snapshot_timestamps");
    return m as ModelOption;
  });
  finite(options.now_ms, 0, Number.MAX_SAFE_INTEGER); finite(options.max_cost, 0, Number.MAX_SAFE_INTEGER); finite(options.deadline_ms, 0, Number.MAX_SAFE_INTEGER);
  const eligible = models.filter(m => m.qualified && m.authorized && m.available_slots > 0 &&
    m.observed_at_ms <= options.now_ms && options.now_ms < m.expires_at_ms && m.cooldown_until_ms <= options.now_ms &&
    options.required.every(v => m.capabilities.includes(v)) && m.estimated_total_cost <= options.max_cost &&
    options.now_ms + m.estimated_latency_ms <= options.deadline_ms && (!options.pinned || m.id === options.pinned));
  eligible.sort((a,b) => a.estimated_total_cost-b.estimated_total_cost || a.estimated_latency_ms-b.estimated_latency_ms || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return eligible[0]?.id ?? null; // Recommendation only; host must reserve and recheck capacity.
}
export function memoryDisposition(route: string, flags: {
  work_requested: boolean; covers_request?: boolean; policy_denied?: boolean;
  human_checkpoint?: boolean; scope_only?: boolean; dependency_required?: boolean;
}): "respond" | "continue_agent" | "await_human" | "blocked" {
  if (Object.values(flags).some(v => typeof v !== "boolean")) throw new Error("memory_flags");
  if (flags.policy_denied) return "blocked";
  if (route === "CLARIFY" || route === "DRAFT") return flags.human_checkpoint ? "await_human" : "blocked";
  if (route === "ANSWER") return flags.covers_request && !flags.work_requested ? "respond" : "continue_agent";
  if (route === "NO_MATCH") return "continue_agent";
  if (route === "DEFLECT") return flags.scope_only ? "continue_agent" : "blocked";
  if (route === "ERROR") return flags.dependency_required ? "blocked" : "continue_agent";
  return "blocked";
}
export function tool<T>(name: string, description: string, argumentSchema: object, parse: (raw: unknown) => T) {
  text(name,128); text(description);
  const schemaHash = fingerprint(argumentSchema);
  return {candidate(raw: unknown, id = name): Candidate {
    const args = parse(raw); fingerprint(args);
    return {id, description, pinned: false, payload: {tool: name,
      arguments: args as never, argument_schema_hash: schemaHash}};
  }}; // Registration only: no callbacks or execution hidden inside the decision layer.
}
