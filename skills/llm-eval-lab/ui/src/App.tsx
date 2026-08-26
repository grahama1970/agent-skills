import { useCallback, useEffect, useMemo, useState } from "react";
import { Play, Pause, Square, RotateCcw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useRegisterAction } from "@/hooks/useRegisterAction";

const APP = "llm-eval-console";
const BLOCKED = "INFRA_BLOCKED";
const POLL_MS = 2000;

interface Trial { trial: number; score: number | null; reason?: string; method?: string; answer?: string; run_dir?: string; }
interface Cell { id: number; model: string; category?: string; status: string; pass_at_1: number | null; pass_at_3: number | null; method?: string | null; trials: Trial[]; }
interface Results { title?: string; models: string[]; status?: string; progress?: { done: number; total: number }; results: Cell[]; }
interface State { running: boolean; paused: boolean; bank: string | null; models: string[]; trials: number; }

const api = {
  get: <T,>(p: string) => fetch(p, { cache: "no-store" }).then((r) => r.json() as Promise<T>),
  post: (p: string, body: unknown) =>
    fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json()),
};

const scoreColor = (s: number | null) =>
  s == null ? "bg-slate-600 text-slate-200" : ["bg-rose-500", "bg-amber-500", "bg-sky-500", "bg-emerald-500"][s] + " text-black";

function bestTrial(c: Cell): Trial {
  const scored = c.trials.filter((t) => t.score != null);
  if (!scored.length) return c.trials[0] ?? { trial: 1, score: null };
  return scored.reduce((a, b) => ((b.score ?? -1) > (a.score ?? -1) ? b : a));
}

/** A run-control button carrying the four best-practices-react attributes. */
function ActionButton(props: {
  qid: string; qsAction: string; title: string; label: string;
  onClick: () => void; disabled?: boolean; variant?: "default" | "secondary" | "danger" | "ghost";
  icon?: React.ReactNode;
}) {
  useRegisterAction({ app: APP, action: props.qsAction, element_id: props.qid, label: props.label });
  return (
    <Button
      data-qid={props.qid}
      data-qs-action={props.qsAction}
      title={props.title}
      onClick={props.onClick}
      disabled={props.disabled}
      variant={props.variant}
      size="sm"
    >
      {props.icon}
      {props.label}
    </Button>
  );
}

function MetricsBar({ res, models }: { res: Results; models: string[] }) {
  const per = useMemo(() => {
    const out: Record<string, { p1: number | null; p3: number | null; blocked: number }> = {};
    for (const m of models) {
      const cells = res.results.filter((r) => r.model === m);
      const valid = cells.filter((r) => r.status !== BLOCKED && r.pass_at_1 != null);
      const blocked = cells.filter((r) => r.status === BLOCKED).length;
      const n = valid.length;
      out[m] = {
        p1: n ? valid.reduce((s, r) => s + (r.pass_at_1 ?? 0), 0) / n : null,
        p3: n ? valid.reduce((s, r) => s + (r.pass_at_3 ?? 0), 0) / n : null,
        blocked,
      };
    }
    return out;
  }, [res, models]);
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `140px repeat(${models.length}, 1fr)` }}>
      <div className="text-xs text-[var(--muted-foreground)] self-center">metric</div>
      {models.map((m) => <div key={m} className="text-xs font-medium truncate" title={m}>{m}</div>)}
      <div className="text-xs text-[var(--muted-foreground)]">avg pass@1</div>
      {models.map((m) => <div key={m} className="text-sm font-semibold">{per[m].p1?.toFixed(2) ?? "—"}</div>)}
      <div className="text-xs text-[var(--muted-foreground)]">avg pass@3</div>
      {models.map((m) => <div key={m} className="text-sm font-semibold">{per[m].p3?.toFixed(2) ?? "—"}</div>)}
      <div className="text-xs text-[var(--muted-foreground)]">infra-blocked</div>
      {models.map((m) => <div key={m} className="text-sm text-amber-400">{per[m].blocked}</div>)}
    </div>
  );
}

function EvidenceCell({ c }: { c: Cell }) {
  if (c.status === BLOCKED) {
    return (
      <td className="border border-[var(--card-border-default)] p-2 align-top bg-amber-950/20">
        <div className="text-amber-400 font-bold text-xs">⚠ INFRA_BLOCKED</div>
        <div className="text-xs text-[var(--muted-foreground)] mt-1">{c.trials[0]?.reason ?? "operational failure"}</div>
        <div className="text-[10px] text-[var(--muted-foreground)] mt-1">excluded from accuracy</div>
      </td>
    );
  }
  const t = bestTrial(c);
  return (
    <td className="border border-[var(--card-border-default)] p-2 align-top">
      <div className="flex items-center gap-2">
        <span className={cn("inline-block min-w-6 text-center font-bold rounded px-1.5 text-sm", scoreColor(t.score))}>{t.score ?? "–"}</span>
        <span className="text-[11px] text-[var(--muted-foreground)]">pass@1 {c.pass_at_1} · pass@3 {c.pass_at_3}</span>
        <span className="text-[10px] border border-white/10 rounded-full px-2 text-[var(--muted-foreground)]">{t.method ?? c.method}</span>
      </div>
      <div className="text-xs mt-1"><b>rationale:</b> {t.reason}</div>
      <details className="mt-1">
        <summary className="cursor-pointer text-xs text-[var(--muted-foreground)]">show raw model response</summary>
        <pre className="mt-1 whitespace-pre-wrap break-words bg-black/40 p-2 rounded text-[11px] max-h-60 overflow-auto">{t.answer || "(empty)"}</pre>
      </details>
      <div className="text-[10px] text-[var(--muted-foreground)] mt-1 break-all">receipt: <code>{t.run_dir}/…/response.md</code></div>
    </td>
  );
}

export default function App() {
  const [models, setModels] = useState<string[]>([]);
  const [banks, setBanks] = useState<string[]>([]);
  const [selModels, setSelModels] = useState<Set<string>>(new Set());
  const [bank, setBank] = useState<string>("");
  const [trials, setTrials] = useState(1);
  const [state, setState] = useState<State | null>(null);
  const [res, setRes] = useState<Results | null>(null);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    api.get<{ models: string[] }>("/api/models").then((d) => setModels(d.models));
    api.get<{ banks: string[] }>("/api/banks").then((d) => { setBanks(d.banks); if (d.banks[0]) setBank(d.banks[0]); });
  }, []);

  useEffect(() => {
    let live = true;
    const tick = async () => {
      try {
        const s = await api.get<State>("/api/state");
        const r = await api.get<Results>("/api/results");
        if (live) { setState(s); setRes(r); }
      } catch { /* transient */ }
      if (live) setTimeout(tick, POLL_MS);
    };
    tick();
    return () => { live = false; };
  }, []);

  const toggleModel = (m: string) => setSelModels((prev) => { const n = new Set(prev); n.has(m) ? n.delete(m) : n.add(m); return n; });

  const run = useCallback(async () => {
    setErr("");
    const r = await api.post("/api/run", { models: [...selModels], bank, trials });
    if (r.error) setErr(r.error);
  }, [selModels, bank, trials]);
  const control = useCallback(async (action: string) => {
    setErr("");
    const r = await api.post("/api/control", { action });
    if (r.error) setErr(r.error);
  }, []);

  const running = state?.running ?? false;
  const paused = state?.paused ?? false;
  const status = res?.status ?? "idle";
  const prog = res?.progress;
  const gridModels = res?.results?.length ? res.models : [...selModels];

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-6 max-w-[1300px] mx-auto">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">LLM Eval Console</h1>
          <p className="text-xs text-[var(--muted-foreground)]">Change models, run evals on question banks, watch results arrive live. Every score cites its /ask run-dir receipt.</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className={cn("inline-block w-2.5 h-2.5 rounded-full", running && !paused ? "bg-emerald-400 animate-pulse" : paused ? "bg-amber-400" : "bg-slate-500")} />
          <span className="text-[var(--muted-foreground)]">
            {running ? (paused ? "paused" : "running") : status}{prog ? ` · ${prog.done}/${prog.total}` : ""}
          </span>
        </div>
      </header>

      <section className="rounded-xl border border-[var(--card-border-default)] bg-[var(--panel)] p-4 mb-4">
        <div className="flex flex-wrap gap-6">
          <div className="min-w-[320px]">
            <div className="text-xs text-[var(--muted-foreground)] mb-2">models ({selModels.size} selected)</div>
            <div className="flex flex-wrap gap-1.5">
              {models.map((m) => {
                const on = selModels.has(m);
                return (
                  <button
                    key={m}
                    data-qid={`console:model:${m}`}
                    data-qs-action="TOGGLE_MODEL"
                    title={`Toggle model ${m}`}
                    onClick={() => toggleModel(m)}
                    disabled={running}
                    className={cn("text-xs rounded-full px-3 py-1 border transition",
                      on ? "bg-[var(--accent)] text-black border-transparent" : "border-white/15 text-[var(--muted-foreground)] hover:border-white/30",
                      running && "opacity-50 cursor-not-allowed")}
                  >{m}</button>
                );
              })}
            </div>
          </div>
          <div>
            <div className="text-xs text-[var(--muted-foreground)] mb-2">question bank</div>
            <select
              data-qid="console:bank:select"
              data-qs-action="SELECT_BANK"
              title="Select question bank"
              value={bank}
              onChange={(e) => setBank(e.target.value)}
              disabled={running}
              className="bg-black/40 border border-white/15 rounded-lg px-3 py-1.5 text-sm"
            >
              {banks.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <div>
            <div className="text-xs text-[var(--muted-foreground)] mb-2">trials</div>
            <input
              data-qid="console:trials:input"
              data-qs-action="SET_TRIALS"
              title="Trials per model/item"
              type="number" min={1} max={5} value={trials}
              onChange={(e) => setTrials(Math.max(1, Math.min(5, Number(e.target.value))))}
              disabled={running}
              className="w-16 bg-black/40 border border-white/15 rounded-lg px-3 py-1.5 text-sm"
            />
          </div>
        </div>
        <div className="flex items-center gap-2 mt-4">
          <ActionButton qid="console:run:start" qsAction="START_RUN" title="Start evaluation run"
            label="Run" icon={<Play size={14} />} onClick={run} disabled={running || selModels.size === 0 || !bank} />
          {!paused
            ? <ActionButton qid="console:run:pause" qsAction="PAUSE_RUN" title="Pause after current cell"
                label="Pause" variant="secondary" icon={<Pause size={14} />} onClick={() => control("pause")} disabled={!running} />
            : <ActionButton qid="console:run:resume" qsAction="RESUME_RUN" title="Resume run"
                label="Resume" variant="secondary" icon={<Play size={14} />} onClick={() => control("resume")} disabled={!running} />}
          <ActionButton qid="console:run:stop" qsAction="STOP_RUN" title="Stop run"
            label="Stop" variant="danger" icon={<Square size={14} />} onClick={() => control("stop")} disabled={!running} />
          <ActionButton qid="console:run:restart" qsAction="RESTART_RUN" title="Restart with same models/bank"
            label="Restart" variant="ghost" icon={<RotateCcw size={14} />} onClick={() => control("restart")} disabled={running || !state?.bank} />
          {running && !paused && <Loader2 size={16} className="animate-spin text-[var(--muted-foreground)]" />}
          {err && <Badge className="bg-rose-500/20 text-rose-200 border-rose-400/30">{err}</Badge>}
        </div>
      </section>

      {res && res.results.length > 0 && (
        <>
          <section className="rounded-xl border border-[var(--card-border-default)] bg-[var(--panel)] p-4 mb-4">
            <MetricsBar res={res} models={gridModels} />
          </section>
          <section className="rounded-xl border border-[var(--card-border-default)] overflow-hidden">
            <table className="w-full border-collapse text-sm">
              <thead><tr>{gridModels.map((m) => <th key={m} className="border border-[var(--card-border-default)] bg-black/30 p-2 text-left text-xs text-[var(--muted-foreground)]">{m}</th>)}</tr></thead>
              <tbody>
                {[...new Set(res.results.map((r) => r.id))].sort((a, b) => a - b).map((id) => {
                  const row = Object.fromEntries(res.results.filter((r) => r.id === id).map((r) => [r.model, r]));
                  const cat = res.results.find((r) => r.id === id)?.category ?? "";
                  return (
                    <>
                      <tr key={`h${id}`}><td colSpan={gridModels.length} className="bg-black/30 border-t-2 border-[var(--accent)] p-2 text-xs"><b className="text-[var(--accent-strong)]">Q{id}</b> <span className="uppercase tracking-wide text-[var(--muted-foreground)] ml-2">{cat}</span></td></tr>
                      <tr key={`r${id}`}>{gridModels.map((m) => row[m] ? <EvidenceCell key={m} c={row[m] as Cell} /> : <td key={m} className="border border-[var(--card-border-default)] p-2 text-[var(--muted-foreground)] text-xs">—</td>)}</tr>
                    </>
                  );
                })}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
