import { Badge } from "../ui/badge";
import type { PopulationViewModel } from "../lib/battle-population-view-model";

function toneToVariant(tone: PopulationViewModel["badges"][number]["tone"]) {
	if (tone === "green") return "green" as const;
	if (tone === "red") return "red" as const;
	if (tone === "amber") return "yellow" as const;
	if (tone === "blue") return "blue" as const;
	if (tone === "purple") return "purple" as const;
	return "default" as const;
}

export function PopulationStatusHeader({ model }: { model: PopulationViewModel }) {
	const { fixture } = model;
	return (
		<header className="battle-proof-panel" data-qid="battle:population:status">
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div className="min-w-0">
					<div className="battle-label">
						{fixture.battle_id.toUpperCase()} · {fixture.proof_mode.replace(/_/g, " ").toUpperCase()}
					</div>
					<h1 className="mt-1 text-2xl font-black tracking-tight text-white" data-qid="battle:population:headline">
						{model.headline}
					</h1>
					<p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{model.subhead}</p>
				</div>
				<div className="text-right">
					<Badge variant="green">{fixture.status}</Badge>
					<div className="mt-2 text-xs uppercase tracking-[0.08em] text-amber-200/90">{model.statusLabel}</div>
					<div className="mt-1 font-mono text-[11px] text-slate-600">
						{fixture.run_id} · {fixture.generated_at}
					</div>
				</div>
			</div>
			<div className="battle-population-banners" data-qid="battle:population:banners">
				{model.banners.map((banner) => (
					<span key={banner.id} className="battle-population-banner" data-tone={banner.tone} data-qid={`battle:population:banner:${banner.id}`}>
						{banner.label}
					</span>
				))}
			</div>
			<div className="mt-3 battle-proof-notice" data-qid="battle:population:boundary-notice">{model.boundaryNotice}</div>
			<div className="mt-3 grid gap-1 text-xs text-slate-400" data-qid="battle:population:campaign">
				<div>
					<span className="battle-label mr-2">campaign</span>
					<span className="font-mono text-slate-200">{model.campaign.id}</span>
				</div>
				<div data-qid="battle:population:campaign:best">
					<span className="battle-label mr-2">best specimen</span>
					<span className="font-mono text-slate-200">{model.campaign.bestSpecimenId}</span>
					<span className="battle-label ml-3 mr-2">verdict</span>
					<span className="text-slate-200">{model.campaign.verdict}</span>
				</div>
				<div data-qid="battle:population:campaign:engine">
					<span className="battle-label mr-2">full_population_engine_proven</span>
					<span className="text-slate-200">false</span>
				</div>
			</div>
			{model.campaign.limitations.length ? (
				<ul className="mt-3 space-y-1 text-sm text-slate-400" data-qid="battle:population:limitations">
					{model.campaign.limitations.map((item) => (
						<li key={item}>{item}</li>
					))}
				</ul>
			) : null}
			<div className="mt-4 flex flex-wrap gap-2" data-qid="battle:population:badges">
				{model.badges.map((badge) => (
					<Badge key={badge.id} variant={toneToVariant(badge.tone)}>
						{badge.label}: {badge.value}
					</Badge>
				))}
			</div>
		</header>
	);
}
