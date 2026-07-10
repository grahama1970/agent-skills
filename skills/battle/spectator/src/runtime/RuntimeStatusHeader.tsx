import { Badge } from "../ui/badge";
import type { RuntimeViewModel } from "../lib/battle-runtime-view-model";

function toneToVariant(tone: RuntimeViewModel["badges"][number]["tone"]) {
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

export function RuntimeStatusHeader({ model }: { model: RuntimeViewModel }) {
	const { fixture } = model;
	return (
		<header className="battle-proof-panel" data-qid="battle:runtime:status">
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div className="min-w-0">
					<div className="battle-label">
						{fixture.battle_id.toUpperCase()} · {fixture.proof_mode.replace(/_/g, " ").toUpperCase()}
					</div>
					<h1 className="mt-1 text-2xl font-black tracking-tight text-white" data-qid="battle:runtime:headline">
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

			<div className="battle-runtime-banners" data-qid="battle:runtime:banners">
				{model.banners.map((banner) => (
					<span key={banner.id} className="battle-runtime-banner" data-tone={banner.tone} data-qid={`battle:runtime:banner:${banner.id}`}>
						{banner.label}
					</span>
				))}
			</div>

			<div className="mt-3 battle-proof-notice" data-qid="battle:runtime:boundary-notice">
				{model.boundaryNotice}
			</div>

			<div className="mt-4 flex flex-wrap gap-2" data-qid="battle:runtime:badges">
				{model.badges.map((badge) => (
					<Badge key={badge.id} variant={toneToVariant(badge.tone)} data-battle-runtime-badge={badge.id}>
						{badge.label}: {badge.value}
					</Badge>
				))}
			</div>
		</header>
	);
}
