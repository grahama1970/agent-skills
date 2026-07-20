import type { BattleAdaptiveLineageMechanicsFixtureV1, BattleNormalizedUxFixture } from "../lib/battle-types";
import { buildLineageComparisonViewModel } from "../lib/battle-lineage-comparison";
import {
	buildAdaptiveLineageViewModel,
	type AdaptiveLineageEdgeView,
	type AdaptiveLineageNodeView,
	type AdaptiveLineageViewModel,
} from "../lib/battle-adaptive-lineage";

type Props = {
	/** Normalized UX fixture (legacy composite parent/child preview path). */
	fixture?: BattleNormalizedUxFixture;
	composite?: boolean;
	/** Adaptive-lineage MECHANICS fixture — renders the genuine G0→{G1}→G2 comparison. */
	adaptiveLineage?: BattleAdaptiveLineageMechanicsFixtureV1;
};

export function BattleLineageComparisonPanel({ fixture, composite = false, adaptiveLineage }: Props) {
	if (adaptiveLineage) {
		const model = buildAdaptiveLineageViewModel(adaptiveLineage);
		if (model) return <AdaptiveLineageComparison model={model} />;
	}
	if (!fixture) return null;
	return <CompositeLineagePreview fixture={fixture} composite={composite} />;
}

function DataSourceBadge({ model }: { model: AdaptiveLineageViewModel }) {
	const amber = model.badge.tone === "amber";
	const cls = amber
		? "border-amber-400/40 bg-amber-500/15 text-amber-100"
		: "border-emerald-400/40 bg-emerald-500/15 text-emerald-100";
	return (
		<span
			className={`rounded border px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.12em] ${cls}`}
			data-qid="battle:adaptive-lineage:badge"
			data-data-source={model.dataSource}
			data-proves-live={model.badge.provesLive ? "true" : "false"}
			title={model.badge.caption}
		>
			{model.badge.label}
		</span>
	);
}

function NodeCard({ node, accent }: { node: AdaptiveLineageNodeView; accent: string }) {
	const outcome = node.judgeOutcome;
	return (
		<div
			className="rounded border border-white/10 bg-white/[0.03] p-2"
			data-qid={`battle:adaptive-lineage:node:${node.id}`}
			data-node-id={node.id}
			data-selected={node.selected ? "true" : "false"}
			data-runner-up={node.runnerUp ? "true" : "false"}
		>
			<div className="flex items-center justify-between gap-2">
				<span className={`text-[11px] font-black uppercase tracking-[0.08em] ${accent}`}>{node.id}</span>
				<span className="text-[9px] uppercase tracking-[0.1em] text-slate-500">gen {node.generation} · {node.role}</span>
			</div>
			{node.mutationOperator ? (
				<div className="mt-1 text-[10px] text-slate-300">
					<span className="font-mono text-cyan-200">{node.mutationOperator}</span>
					{typeof node.noveltyDistance === "number" ? (
						<span className="text-slate-500"> · novelty {node.noveltyDistance}</span>
					) : null}
				</div>
			) : (
				<div className="mt-1 text-[10px] text-slate-500">seed exploit · no mutation</div>
			)}
			{node.techniqueDelta ? <div className="mt-1 text-[10px] text-slate-400">{node.techniqueDelta}</div> : null}
			{node.changedDimensionNames.length ? (
				<div className="mt-1 flex flex-wrap gap-1" data-qid={`battle:adaptive-lineage:node:${node.id}:dimensions`}>
					{node.changedDimensionNames.map((dim) => (
						<span key={dim} className="rounded bg-violet-500/15 px-1 py-0.5 text-[9px] font-mono text-violet-100">
							{dim}
						</span>
					))}
				</div>
			) : null}
			{outcome ? (
				<div className="mt-1 text-[9px] text-slate-500">
					vuln-original {outcome.vulnerable_original_confirmed ? "yes" : "no"} · bypass {outcome.patched_bypass ? "yes" : "no"} · {outcome.duration_seconds}s
					{node.fitnessStatus ? <span className="text-slate-400"> · fitness {node.fitnessStatus}</span> : null}
				</div>
			) : null}
		</div>
	);
}

function EdgeRow({ edge }: { edge: AdaptiveLineageEdgeView }) {
	return (
		<li className="text-[10px] text-slate-300" data-qid={`battle:adaptive-lineage:edge:${edge.id}`} data-edge={edge.id}>
			<span className="font-mono text-slate-400">{edge.from}→{edge.to}</span>
			<span className="text-slate-500"> · {edge.label}</span>
		</li>
	);
}

function AdaptiveLineageComparison({ model }: { model: AdaptiveLineageViewModel }) {
	const passed = model.qualification.passed;
	return (
		<details
			className="group border-b border-white/10 bg-[#0d1117]"
			data-qid="battle:lineage-comparison"
			data-mode="adaptive"
			aria-label="Adaptive lineage mechanics comparison"
		>
			{/* Collapsed by default: a single scannable summary row so the panel does not
			    crowd the race shell. Expand to see the full G0→{G1}→G2 comparison. */}
			<summary className="battle-lineage-subnav sub-nav-wrapper flex cursor-pointer list-none items-center px-4 text-[10px]">
				<div className="top-nav-left-cluster">
					{/* MODULE 1 — view mode */}
					<div className="nav-module mode-indicator">
						<svg className="mode-icon" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" aria-hidden="true">
							<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 3v12a3 3 0 003 3h9m0 0l-3-3m3 3l-3 3M6 6a3 3 0 100-.01" />
						</svg>
						<span className="module-title">Adaptive Lineage</span>
					</div>
					{/* MODULE 2 — consolidated data-source + qualification status LED */}
					<div
						className="nav-module system-status"
						data-qid="battle:adaptive-lineage:qualification"
						data-status={model.qualification.status}
						data-data-source={model.dataSource}
						data-proves-live={model.badge.provesLive ? "true" : "false"}
						title={model.badge.caption}
					>
						<span className={`status-led ${passed && model.badge.tone !== "amber" ? "led-live" : "led-idle"}`} data-qid="battle:adaptive-lineage:badge" />
						<span className="status-text">{model.badge.label}: Qual {model.qualification.status}</span>
					</div>
					{/* MODULE 3 — muted lineage breadcrumb */}
					<div className="nav-module context-breadcrumb">
						<span className="node">{model.selection.selectedId ?? "—"}</span>
						<span className="divider">/</span>
						<span className="node runner">{model.selection.runnerUpId ?? "—"}</span>
						<span className="metadata">· {model.selection.decidingCriterion ?? "—"}</span>
					</div>
				</div>
				<div className="top-nav-right-cluster">
					<div className="nav-module view-toggle">
						<span className="minimal-toggle-btn">
							<span className="toggle-icon transition-transform group-open:rotate-90">▸</span>
							<span className="toggle-label group-open:hidden">show</span>
							<span className="toggle-label hidden group-open:inline">hide</span>
						</span>
					</div>
				</div>
			</summary>

			<div className="border-t border-white/10 px-3 pb-3 pt-2">
			{/* G0 seed → {G1-A, G1-B} candidates → G2 descendant */}
			<div className="space-y-2">
				{model.seed ? <NodeCard node={model.seed} accent="text-slate-200" /> : null}
				<div className="grid gap-2 md:grid-cols-2">
					{model.candidates.map((node) => (
						<div
							key={node.id}
							data-qid={
								node.selected
									? "battle:adaptive-lineage:selected"
									: node.runnerUp
										? "battle:adaptive-lineage:runner-up"
										: `battle:adaptive-lineage:candidate:${node.id}`
							}
						>
							<NodeCard node={node} accent={node.selected ? "text-emerald-200" : "text-amber-200"} />
							<div className="mt-0.5 text-[9px] uppercase tracking-[0.1em] text-slate-500">
								{node.selected ? "SELECTED G1" : node.runnerUp ? "RUNNER-UP G1" : "candidate"}
							</div>
						</div>
					))}
				</div>
				{model.descendant ? <NodeCard node={model.descendant} accent="text-violet-200" /> : null}
			</div>

			<div
				className="mt-2 rounded border border-white/10 bg-white/[0.02] p-2 text-[10px] text-slate-300"
				data-qid="battle:adaptive-lineage:deciding-criterion"
				data-selected-id={model.selection.selectedId ?? ""}
				data-runner-up-id={model.selection.runnerUpId ?? ""}
				data-deciding-criterion={model.selection.decidingCriterion ?? ""}
			>
				Selection: <span className="font-mono text-emerald-200">{model.selection.selectedId ?? "—"}</span> over{" "}
				<span className="font-mono text-amber-200">{model.selection.runnerUpId ?? "—"}</span> · deciding criterion{" "}
				<span className="font-mono text-cyan-200">{model.selection.decidingCriterion ?? "—"}</span>
			</div>

			<div className="mt-2" data-qid="battle:adaptive-lineage:edges">
				<div className="text-[10px] font-black uppercase tracking-[0.08em] text-slate-400">Mutation edges</div>
				<ul className="mt-1 space-y-0.5">
					{model.edges.map((edge) => (
						<EdgeRow key={edge.id} edge={edge} />
					))}
				</ul>
			</div>

			{!model.badge.provesLive ? (
				<div className="mt-2 text-[10px] text-amber-200/80" data-qid="battle:adaptive-lineage:honesty">
					Recorded mechanics only — does not prove a live adaptive canary.
				</div>
			) : null}
			</div>
		</details>
	);
}

function CompositeLineagePreview({ fixture, composite }: { fixture: BattleNormalizedUxFixture; composite: boolean }) {
	const model = buildLineageComparisonViewModel(fixture, composite);
	if (!model) return null;
	return (
		<section className="rounded-lg border border-white/10 bg-black/25 p-3" data-qid="battle:lineage-comparison" aria-label="Parent child lineage comparison">
			<div className="flex flex-wrap items-center gap-2">
				<span className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">Parent / child comparison</span>
				{composite ? (
					<span className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.1em] text-amber-100" data-qid="battle:lineage-comparison:composite">
						PREVIEW · NOT ADAPTIVE CANARY
					</span>
				) : null}
			</div>
			<div className="mt-2 grid gap-2 md:grid-cols-2">
				<div className="rounded border border-white/10 bg-white/[0.03] p-2" data-qid="battle:lineage-comparison:parent">
					<div className="text-[10px] font-black uppercase tracking-[0.08em] text-cyan-200">Parent</div>
					<div className="text-[12px] text-slate-200">{model.parent?.name ?? "not emitted"}</div>
					<div className="text-[10px] text-slate-500">{model.parent?.laneId ?? "—"} · gen {model.parent?.generation ?? "—"}</div>
				</div>
				<div className="rounded border border-white/10 bg-white/[0.03] p-2" data-qid="battle:lineage-comparison:child">
					<div className="text-[10px] font-black uppercase tracking-[0.08em] text-violet-200">Child</div>
					<div className="text-[12px] text-slate-200">{model.child?.name ?? "not emitted"}</div>
					<div className="text-[10px] text-slate-500">{model.child?.laneId ?? "—"} · gen {model.child?.generation ?? "—"}</div>
				</div>
			</div>
			<div className="mt-2 grid gap-2 md:grid-cols-2">
				<div data-qid="battle:lineage-comparison:inherited">
					<div className="text-[10px] font-black uppercase tracking-[0.08em] text-emerald-300/80">Inherited (fixture-listed)</div>
					<ul className="mt-1 space-y-0.5 text-[11px] text-slate-300">
						{model.inherited.slice(0, 6).map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
				<div data-qid="battle:lineage-comparison:new">
					<div className="text-[10px] font-black uppercase tracking-[0.08em] text-amber-200/80">Changed / unknown</div>
					<ul className="mt-1 space-y-0.5 text-[11px] text-slate-300">
						{model.newOrUnknown.map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
			</div>
			<div className="mt-2 text-[10px] text-slate-500" data-qid="battle:lineage-comparison:questions">
				Viewer questions: {model.questions.join(" · ")}
			</div>
			<div className="mt-1 text-[10px] text-rose-200/80" data-qid="battle:lineage-comparison:does-not-prove">
				Does not prove: {model.doesNotProve.slice(0, 4).join("; ")}
			</div>
		</section>
	);
}
