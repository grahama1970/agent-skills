import { Badge } from "../ui/badge";
import type { ProofCardViewModel } from "../lib/battle-proof-card-view-model";

function toneToVariant(tone: ProofCardViewModel["badges"][number]["tone"]) {
	if (tone === "green") return "green" as const;
	if (tone === "red") return "red" as const;
	if (tone === "amber") return "yellow" as const;
	if (tone === "blue") return "blue" as const;
	if (tone === "purple") return "purple" as const;
	return "default" as const;
}

function statusVariant(status: string) {
	const upper = status.toUpperCase();
	if (upper === "PASS") return "green" as const;
	if (upper === "BLOCKED") return "yellow" as const;
	if (upper === "FAIL") return "red" as const;
	return "purple" as const;
}

export function ProofCardHeader({ model }: { model: ProofCardViewModel }) {
	const { fixture } = model;
	return (
		<header className="battle-proof-panel" data-qid="battle:proof-card:status">
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div className="min-w-0">
					<div className="battle-label">
						{fixture.battle_id.toUpperCase()} · {fixture.proof_mode.replace(/_/g, " ").toUpperCase()}
					</div>
					<h1 className="mt-1 text-2xl font-black tracking-tight text-white" data-qid="battle:proof-card:headline">
						{model.headline}
					</h1>
					<p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{model.subhead}</p>
				</div>
				<div className="text-right">
					<Badge variant={statusVariant(fixture.status)}>{fixture.status}</Badge>
					<div className="mt-2 text-xs uppercase tracking-[0.08em] text-amber-200/90">{model.statusLabel}</div>
					<div className="mt-1 font-mono text-[11px] text-slate-600">
						{fixture.run_id} · {fixture.generated_at ?? "not emitted"}
					</div>
				</div>
			</div>

			<div
				className="mt-3 grid gap-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-slate-400"
				data-qid="battle:proof-card:execution-boundary"
			>
				<div>
					<span className="battle-label mr-2">Live Tau / browser execution</span>
					<span className="text-violet-200">
						{fixture.tau_execution === "attempted" || fixture.live === "tau_dag_runtime" ? "yes — command-spec DAG canary" : "not emitted"}
					</span>
				</div>
				<div data-qid="battle:proof-card:boundary:external-tool">
					<span className="battle-label mr-2">external_tool_called</span>
					<span className="text-slate-200">{model.research.externalToolCalled ? "true" : "false"}</span>
				</div>
				<div data-qid="battle:proof-card:boundary:provider-live">
					<span className="battle-label mr-2">provider_live</span>
					<span className="text-slate-200">{model.research.providerLive || model.genome.providerLive ? "true" : "false"}</span>
				</div>
				<div data-qid="battle:proof-card:boundary:exploit-code-generated">
					<span className="battle-label mr-2">exploit code generated</span>
					<span className="text-slate-200">false</span>
				</div>
			</div>
			<div className="mt-4 flex flex-wrap gap-2" data-qid="battle:proof-card:badges">
				{model.badges.map((badge) => (
					<Badge key={badge.id} variant={toneToVariant(badge.tone)} data-battle-proof-badge={badge.id}>
						{badge.label}: {badge.value}
					</Badge>
				))}
			</div>
		</header>
	);
}
