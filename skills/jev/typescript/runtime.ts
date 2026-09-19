/** Native Jev decisions. No Python bridge, arbitrary execution or hidden retries. */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

export type JSONValue = null | boolean | number | string | JSONValue[] | { [key: string]: JSONValue };
type Obj = Record<string, any>;
export const CONTRACT = JSON.parse(readFileSync(new URL("../jev_runtime/contract.json", import.meta.url), "utf8"));
export interface Policy {
  allow_egress: boolean; data_class: "public" | "approved_internal" | "restricted" | "unknown";
  threshold: number; timeout_ms: number; blocked_terms: string[];
}
export interface Request { task: string; state: JSONValue; questions: Record<string, Obj>; model: string }
export interface Decision {
  schema_version: "jev.decision.v1"; status: "accepted" | "abstain" | "blocked" | "error";
  reason: string; request_hash: string; policy_hash: string; requested_model: string;
  resolved_model: string | null; answers: Record<string, Obj>; confident: string[];
  usage: Record<string, number> | null; duration_ms: number;
  validation_errors: {type: string; loc: string[]; msg: string}[];
}
export interface Candidate {id: string; description: string; payload: Record<string, JSONValue>; pinned: boolean}
export interface Selection {status: "selected" | "no_match" | "abstain" | "error" | "blocked"; ids: string[]; excluded: string[]; uncertain: string[]; receipt: Decision | null}
export type Transport = (body: Obj, signal: AbortSignal) => Promise<unknown>;

export function record(v: unknown): Obj {
  if (v === null || typeof v !== "object" || Array.isArray(v)) throw new Error("object_required");
  return v as Obj;
}
export function keys(v: Obj, allowed: string[], required = allowed): void {
  if (Object.keys(v).some(k => !allowed.includes(k)) || required.some(k => !Object.hasOwn(v, k))) throw new Error("object_keys");
}
export function text(v: unknown, max = 16000): asserts v is string {
  if (typeof v !== "string" || v.length < 1 || v.length > max) throw new Error("string_domain");
}
export function finite(v: unknown, min: number, max: number): asserts v is number {
  if (typeof v !== "number" || !Number.isFinite(v) || v < min || v > max) throw new Error("number_domain");
}
export function policy(value: unknown = {}): Policy {
  const p = {allow_egress: false, data_class: "unknown", threshold: 0.98, timeout_ms: 1500, blocked_terms: [], ...record(value)};
  keys(p, ["allow_egress", "data_class", "threshold", "timeout_ms", "blocked_terms"]);
  if (typeof p.allow_egress !== "boolean" || !["public", "approved_internal", "restricted", "unknown"].includes(p.data_class)) throw new Error("policy_domain");
  finite(p.threshold, 0.5, 1); if (p.threshold === 0.5) throw new Error("threshold_domain");
  finite(p.timeout_ms, 100, 10000); if (!Number.isInteger(p.timeout_ms)) throw new Error("timeout_domain");
  if (!Array.isArray(p.blocked_terms) || p.blocked_terms.some((x: unknown) => typeof x !== "string")) throw new Error("blocked_terms");
  return structuredClone(p) as Policy;
}

function codepointOrder(a: string, b: string): number {
  const aa = Array.from(a), bb = Array.from(b);
  for (let i = 0; i < Math.min(aa.length, bb.length); i++) {
    const d = aa[i].codePointAt(0)! - bb[i].codePointAt(0)!; if (d) return d;
  }
  return aa.length - bb.length;
}
export function fingerprint(value: unknown): string {
  function encode(v: unknown): unknown {
    if (v === null) return ["null"];
    if (typeof v === "boolean") return ["bool", v];
    if (typeof v === "number") {
      if (!Number.isFinite(v) || (Number.isInteger(v) && !Number.isSafeInteger(v))) throw new Error("unsupported_number");
      const b = Buffer.alloc(8); b.writeDoubleBE(v || 0); return ["number", b.toString("hex")];
    }
    if (typeof v === "string") {
      for (const c of v) {const cp = c.codePointAt(0)!; if (cp >= 0xd800 && cp <= 0xdfff) throw new Error("invalid_unicode");}
      return ["string", v];
    }
    if (Array.isArray(v)) return ["array", v.map(encode)];
    if (v && typeof v === "object" && Object.getPrototypeOf(v) === Object.prototype)
      return ["object", Object.keys(v).sort(codepointOrder).map(k => [encode(k), encode((v as Obj)[k])])];
    throw new Error("not_json");
  }
  return createHash("sha256").update(JSON.stringify(encode(value))).digest("hex");
}
export function validateRequest(value: unknown): Request {
  const r = record(value); keys(r, ["task", "state", "questions", "model"]); text(r.task, 128); text(r.model, 128);
  const qs = record(r.questions);
  if (Object.keys(qs).length < 1 || Object.keys(qs).length > CONTRACT.max_questions) throw new Error("question_count");
  for (const [id, raw] of Object.entries(qs)) {
    text(id); const q = record(raw); keys(q, ["type", "instructions", "criteria"], ["type"]);
    if (q.type === "choice") {if (Object.keys(record(q.criteria)).length < 2) throw new Error("choice_criteria");}
    else if (q.type === "score") {if (!Array.isArray(q.criteria) || q.criteria.length < 2) throw new Error("score_criteria");}
    else if (q.type === "noul") {if (q.criteria != null) keys(record(q.criteria), ["true", "false"], []);}
    else throw new Error("question_type");
  }
  fingerprint(r); return structuredClone(r) as Request;
}
export function egressReason(body: unknown, p: Policy): string | null {
  if (!p.allow_egress || !["public", "approved_internal"].includes(p.data_class)) return "egress_not_authorized";
  const s = JSON.stringify(body);
  if (Buffer.byteLength(s) > CONTRACT.max_payload_bytes) return "payload_budget";
  if ([...CONTRACT.blocked_markers, ...p.blocked_terms].some((x: string) => x && s.toLowerCase().includes(x.toLowerCase()))) return "restricted_payload";
  return null;
}
export function validateResponse(req: Request, value: unknown): Obj {
  fingerprint(value); const r = record(value);
  keys(r, ["model", "answers", "usage"], ["model", "answers"]); text(r.model);
  if (req.model !== "jev-latest" && r.model !== req.model) throw new Error("model_binding");
  keys(record(r.answers), Object.keys(req.questions));
  if (r.usage != null) for (const v of Object.values(record(r.usage))) {finite(v, 0, Number.MAX_SAFE_INTEGER); if (!Number.isInteger(v)) throw new Error("usage_domain");}
  for (const [id, raw] of Object.entries(r.answers)) {
    const a = record(raw), q = req.questions[id];
    if (a.type !== q.type) throw new Error("answer_type");
    if (a.type === "noul") {keys(a, ["type", "noul"]); finite(a.noul, 0, 1); continue;}
    keys(a, a.type === "choice" ? ["type", "choice", "confidence", "probabilities"] : ["type", "score", "confidence", "probabilities", "legend"],
      a.type === "choice" ? ["type", "choice", "confidence", "probabilities"] : ["type", "score", "confidence", "probabilities"]);
    finite(a.confidence, 0, 1);
    const labels = a.type === "choice" ? Object.keys(q.criteria) : q.criteria.map((_: unknown, i: number) => String(i));
    keys(record(a.probabilities), labels);
    const ps = Object.values(a.probabilities) as number[]; ps.forEach(v => finite(v, 0, 1));
    if (Math.abs(ps.reduce((s, p) => s + p, 0) - 1) > 0.001) throw new Error("probability_sum");
    if (a.type === "choice") {
      if (typeof a.choice !== "string" || !labels.includes(a.choice) || a.probabilities[a.choice] + 1e-9 < Math.max(...ps)) throw new Error("choice_domain");
    } else {
      const expected = Object.entries(a.probabilities).reduce((s, [k, p]) => s + Number(k) * (p as number), 0);
      finite(a.score, 0, labels.length - 1);
      if (Math.abs(expected - a.score) > 0.001) throw new Error("score_domain");
      if (a.legend != null && fingerprint(a.legend) !== fingerprint(Object.fromEntries(q.criteria.map((v: unknown, i: number) => [String(i), v])))) throw new Error("score_legend");
    }
  }
  return r;
}
export function confidentIds(response: Obj, threshold: number): string[] {
  return Object.entries(response.answers).filter(([, raw]) => {
    const a = raw as Obj;
    return a.type === "noul" ? a.noul >= threshold || a.noul <= 1-threshold :
      a.confidence >= threshold && (a.type !== "choice" || a.probabilities[a.choice] >= threshold);
  }).map(([id]) => id);
}

export class Jev {
  readonly policy: Policy; private transport?: Transport; private sdk: any;
  constructor(value: unknown = {}, transport?: Transport) {this.policy = policy(value); this.transport = transport;}
  private async send(body: Obj, signal: AbortSignal): Promise<unknown> {
    if (this.transport) return this.transport(body, signal);
    if (!this.sdk) {
      const packageName = "@typesafe-ai/sdk";
      const sdk = await import(packageName);
      this.sdk = new sdk.TypeSafeClient({apiKey: process.env.JEV_API_KEY || process.env.TYPESAFE_API_KEY,
        baseURL: "https://api.typesafe.ai", logLevel: "off", retry: {maxRetries: 0}, timeout: this.policy.timeout_ms});
    }
    return await this.sdk.systemOne(body, {signal, retry: {maxRetries: 0}});
  }
  async ask(value: Request, options: {required?: string[]; signal?: AbortSignal} = {}): Promise<Decision> {
    const req = validateRequest(value), p = policy(this.policy), needed = options.required ?? Object.keys(req.questions);
    if (!needed.length || needed.some(id => !Object.hasOwn(req.questions, id))) throw new Error("required_questions");
    const start = performance.now();
    const base = {schema_version: "jev.decision.v1" as const, request_hash: fingerprint(req), policy_hash: fingerprint(p),
      requested_model: req.model, resolved_model: null, answers: {}, confident: [], usage: null, validation_errors: []};
    const finish = (status: Decision["status"], reason: string, rest: Partial<Decision> = {}): Decision =>
      ({...base, status, reason, duration_ms: performance.now()-start, ...rest});
    const body = {state: req.state, questions: req.questions, model: req.model};
    const blocked = egressReason(body, p); if (blocked) return finish("blocked", blocked);
    const signal = AbortSignal.any([AbortSignal.timeout(p.timeout_ms), ...(options.signal ? [options.signal] : [])]);
    if (signal.aborted) return finish("abstain", "cancelled");
    let raw: unknown;
    try {
      let abort: (() => void) | undefined;
      try {
        raw = await Promise.race([this.send(body, signal), new Promise<never>((_resolve,reject) => {
          abort = () => reject(new Error("cancelled")); signal.addEventListener("abort",abort,{once:true});
          if(signal.aborted) abort();
        })]);
      } finally {if(abort) signal.removeEventListener("abort",abort);}
      if (signal.aborted) return finish("abstain", options.signal?.aborted ? "cancelled" : "deadline");
    } catch {return finish(signal.aborted ? "abstain" : "error", signal.aborted ? options.signal?.aborted ? "cancelled" : "deadline" : "provider_error");}
    let response: Obj;
    try {response = validateResponse(req, raw);} catch {
      return finish("error", "invalid_response", {validation_errors: [{type: "response_validation", loc: [], msg: "Response violates submitted question contract"}]});
    }
    const confident = confidentIds(response, p.threshold), accepted = needed.every(id => confident.includes(id));
    return finish(accepted ? "accepted" : "abstain", accepted ? "qualified" : "uncertain", {
      answers: response.answers, confident, resolved_model: response.model, usage: response.usage ?? null});
  }
}

export function candidates(value: unknown): Candidate[] {
  if (!Array.isArray(value) || value.length > CONTRACT.max_candidates) throw new Error("candidate_count");
  const result = value.map(raw => {
    const c: Obj = {payload: {}, pinned: false, ...record(raw)}; keys(c, ["id", "description", "payload", "pinned"]);
    text(c.id,128); text(c.description); record(c.payload); if (typeof c.pinned !== "boolean" || c.id === "no_match") throw new Error("candidate_domain");
    fingerprint(c); return structuredClone(c) as Candidate;
  });
  if (new Set(result.map(c => c.id)).size !== result.length) throw new Error("candidate_duplicates");
  return result;
}
function empty(): Selection {return {status: "no_match", ids: [], excluded: [], uncertain: [], receipt: null};}
export async function select(jev: Jev, state: JSONValue, input: Candidate[], task = "tool", model = "jev-latest", signal?: AbortSignal): Promise<Selection> {
  const cs = candidates(input); if (!cs.length) return empty();
  const receipt = await jev.ask({task, state: {task: state, candidates: cs as unknown as JSONValue}, model,
    questions: {selection: {type: "choice", instructions: CONTRACT.selection_instruction,
      criteria: Object.fromEntries([...cs.map(c => [c.id, c.description]), ["no_match", "No candidate satisfies the request."]])}}}, {signal});
  if (receipt.status !== "accepted") return {...empty(), status: receipt.status, receipt};
  const id = receipt.answers.selection.choice;
  return {...empty(), status: id === "no_match" ? "no_match" : "selected", ids: id === "no_match" ? [] : [id], receipt};
}
export async function rank(jev: Jev, state: JSONValue, input: Candidate[], task = "memory_relevance", model = "jev-latest", signal?: AbortSignal): Promise<Selection> {
  const cs = candidates(input); if (!cs.length) return empty();
  const receipt = await jev.ask({task, state: {task: state, candidates: cs as unknown as JSONValue}, model,
    questions: Object.fromEntries(cs.map((_, i) => [`c${i}`, {type: "noul", instructions: CONTRACT.relevance_instruction.replace("{index}", String(i))}]))}, {signal});
  if (receipt.status === "error" || receipt.status === "blocked" || !Object.keys(receipt.answers).length)
    return {...empty(), status: receipt.status === "accepted" ? "error" : receipt.status, ids: cs.map(c => c.id), uncertain: cs.map(c => c.id), receipt};
  const excluded: string[] = [], uncertain: string[] = [];
  const kept = cs.map((c,i) => ({c,i,p: receipt.answers[`c${i}`].noul as number})).filter(({c,i,p}) => {
    const certain = receipt.confident.includes(`c${i}`); if (!certain) uncertain.push(c.id);
    if (!c.pinned && certain && p < 0.5) {excluded.push(c.id); return false;} return true;
  }).sort((a,b) => b.p-a.p || a.i-b.i);
  return {status: uncertain.length ? "abstain" : kept.length ? "selected" : "no_match", ids: kept.map(x => x.c.id), excluded, uncertain, receipt};
}

export async function classify(jev: Jev, state: JSONValue, model = "jev-latest", signal?: AbortSignal): Promise<Decision> {
  return jev.ask({task:"harness_classification",state,model,questions:Object.fromEntries(["intents","capabilities"].map(name=>[name,{
    type:"choice",instructions:"Classify the actual request; choose no_match if uncertain or unsupported.",
    criteria:{...CONTRACT[name],no_match:"None of the specified categories fits."}
  }]))},{signal});
}
