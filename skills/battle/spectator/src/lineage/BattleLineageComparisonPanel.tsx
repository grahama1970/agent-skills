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
	sourceBound?: boolean;
	/** Adaptive-lineage MECHANICS fixture — renders the genuine G0→{G1}→G2 comparison. */
	adaptiveLineage?: BattleAdaptiveLineageMechanicsFixtureV1;
};

export function BattleLineageComparisonPanel({ fixture, composite = false, sourceBound = false, adaptiveLineage }: Props) {
	if (adaptiveLineage) {
		const model = buildAdaptiveLineageViewModel(adaptiveLineage);
		if (model) return <AdaptiveLineageComparison model={model} />;
	}
	if (!fixture) return null;
	if (sourceBound) return <ReceiptBoundAdaptiveLineagePanel fixture={fixture} />;
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
		<section
			className="rounded-lg border border-white/10 bg-black/25 p-3"
			data-qid="battle:lineage-comparison"
			data-mode="adaptive"
			aria-label="Adaptive lineage mechanics comparison"
		>
			<div className="flex flex-wrap items-center gap-2">
				<span className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">Adaptive lineage · mechanics</span>
				<DataSourceBadge model={model} />
				<span
					className={`rounded border px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.1em] ${
						passed ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100" : "border-rose-400/30 bg-rose-500/10 text-rose-100"
					}`}
					data-qid="battle:adaptive-lineage:qualification"
					data-status={model.qualification.status}
				>
					QUALIFICATION {model.qualification.status}
					{model.qualification.stopCondition ? ` · ${model.qualification.stopCondition}` : ""}
				</span>
			</div>

			{/* G0 seed → {G1-A, G1-B} candidates → G2 descendant */}
			<div className="mt-2 space-y-2">
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
		</section>
	);
}

function shortHash(hash?: string): string {
	if (!hash) return "hash unavailable";
	return hash.slice(0, 12);
}

function receiptLabel(ref?: { receipt_id?: string | null; sha256?: string; schema?: string } | null): string {
	if (!ref) return "receipt missing";
	return ref.receipt_id ?? `${ref.schema ?? "receipt"}:${(ref.sha256 ?? "").slice(0, 12)}`;
}

function ReceiptBoundAdaptiveLineagePanel({ fixture }: { fixture: BattleNormalizedUxFixture }) {
	const source = fixture.adaptive_lineage_panel_source;
	if (!source || source.status !== "PASS" || !source.mechanics_trees) {
		return (
			<section
				className="rounded-lg border border-amber-400/25 bg-amber-950/20 p-3"
				data-qid="battle:lineage-comparison"
				data-mode="proof-unavailable"
				data-battle-id={fixture.battle_id}
				data-run-id={fixture.run_id ?? ""}
				data-source-proof-id={fixture.source_proof_id ?? ""}
				data-source-fixture-id={source?.fixture_id ?? fixture.fixture_id ?? ""}
				data-source-fixture-sha256={fixture.source_fixture_sha256 ?? ""}
				data-proves-live="false"
				aria-label="Adaptive lineage mechanics proof unavailable"
			>
				<div className="flex flex-wrap items-center gap-2">
					<span className="text-[10px] font-black uppercase tracking-[0.12em] text-amber-100">Adaptive lineage · proof unavailable</span>
					<span
						className="rounded border border-amber-400/40 bg-amber-500/15 px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.12em] text-amber-100"
						data-qid="battle:adaptive-lineage:badge"
						data-data-source={source?.fixture_id ?? fixture.fixture_id ?? "unbound"}
						data-proves-live="false"
						title="The loaded receipt fixture did not expose canonical adaptive mechanics trees."
					>
						NO MECHANICS SOURCE
					</span>
				</div>
				<div className="mt-2 grid gap-2 text-[10px] text-slate-300 md:grid-cols-4">
					<div data-qid="battle:adaptive-lineage:source:battle-id">battle_id: {source?.battle_id ?? fixture.battle_id}</div>
					<div data-qid="battle:adaptive-lineage:source:run-id">run_id: {source?.run_id ?? fixture.run_id ?? "not emitted"}</div>
					<div data-qid="battle:adaptive-lineage:source:proof-id">proof_id: {source?.source_proof_id ?? fixture.source_proof_id ?? "not emitted"}</div>
					<div data-qid="battle:adaptive-lineage:source:hash">sha256: {shortHash(source?.source_fixture_sha256 ?? fixture.source_fixture_sha256)}</div>
				</div>
				<div className="mt-2 text-[10px] text-amber-100/80" data-qid="battle:adaptive-lineage:unavailable-reason">
					{source?.reason ?? "Loaded race fixture is not hash-bound to an adaptive mechanics source."}
				</div>
			</section>
		);
	}
	return <CanonicalDualTeamMechanicsPanel source={source} />;
}

function CanonicalDualTeamMechanicsPanel({
	source,
}: {
	source: NonNullable<BattleNormalizedUxFixture["adaptive_lineage_panel_source"]>;
}) {
	const teams = source.mechanics_trees?.teams;
	const scoreboard = source.scoreboard;
	const contract = source.canonical_dual_team_contract;
	return (
		<section
			className="rounded-lg border border-white/10 bg-black/25 p-3"
			data-qid="battle:lineage-comparison"
			data-mode="canonical-dual-team"
			data-battle-id={source.battle_id}
			data-run-id={source.run_id}
			data-source-proof-id={source.source_proof_id}
			data-source-fixture-id={source.fixture_id}
			data-source-fixture-sha256={source.source_fixture_sha256 ?? ""}
			data-proves-live="false"
			aria-label="Adaptive lineage mechanics comparison"
		>
			<div className="flex flex-wrap items-center gap-2">
				<span className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">Adaptive lineage · loaded receipt source</span>
				<span
					className="rounded border border-emerald-400/40 bg-emerald-500/15 px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.12em] text-emerald-100"
					data-qid="battle:adaptive-lineage:badge"
					data-data-source={source.fixture_id}
					data-proves-live="false"
					title="Canonical mechanics are derived from the currently loaded receipt fixture."
				>
					RECEIPT SOURCE
				</span>
				<span
					className="rounded border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.1em] text-cyan-100"
					data-qid="battle:adaptive-lineage:qualification"
					data-status={contract?.status ?? source.status}
				>
					CONTRACT {contract?.status ?? source.status}
				</span>
			</div>
			<div className="mt-2 grid gap-2 text-[10px] text-slate-300 md:grid-cols-5">
				<div data-qid="battle:adaptive-lineage:source:battle-id">battle_id: {source.battle_id}</div>
				<div data-qid="battle:adaptive-lineage:source:run-id">run_id: {source.run_id}</div>
				<div data-qid="battle:adaptive-lineage:source:proof-id">proof_id: {source.source_proof_id}</div>
				<div data-qid="battle:adaptive-lineage:source:hash">sha256: {shortHash(source.source_fixture_sha256)}</div>
				<div data-qid="battle:adaptive-lineage:source:score">score red {scoreboard?.red_score ?? "—"} · blue {scoreboard?.blue_score ?? "—"}</div>
			</div>
			<div className="mt-2 grid gap-2 md:grid-cols-2">
				{(["red", "blue"] as const).map((team) => {
					const tree = teams?.[team];
					return (
						<div key={team} className="rounded border border-white/10 bg-white/[0.03] p-2" data-qid={`battle:adaptive-lineage:team:${team}`}>
							<div className={`text-[10px] font-black uppercase tracking-[0.08em] ${team === "red" ? "text-rose-200" : "text-cyan-200"}`}>
								{team} mechanics
							</div>
							<div className="mt-1 grid gap-1">
								{(tree?.nodes ?? []).map((node) => (
									<div
										key={node.lane_id}
										className="rounded border border-white/10 bg-black/20 p-2"
										data-qid={`battle:adaptive-lineage:canonical-node:${node.lane_id}`}
										data-source-lane-id={node.lane_id}
										data-team={node.team}
										data-parent-lane-id={node.parent_lane_id ?? ""}
										data-selection-disposition={node.selection_disposition}
									>
										<div className="flex items-center justify-between gap-2">
											<span className="font-mono text-[11px] text-slate-100">{node.lane_id}</span>
											<span className="text-[9px] uppercase tracking-[0.1em] text-slate-500">gen {node.generation} · {node.role}</span>
										</div>
										<div className="mt-0.5 text-[10px] text-slate-400">
											{node.mutation_operator ?? "mutation not emitted"} · {node.selection_disposition}
										</div>
										<div className="mt-0.5 text-[9px] text-slate-500">
											{receiptLabel(node.observation_receipt_ref)} · {receiptLabel(node.fitness_receipt_ref)}
										</div>
									</div>
								))}
							</div>
							<ul className="mt-2 space-y-1" data-qid={`battle:adaptive-lineage:canonical-edges:${team}`}>
								{(tree?.edges ?? []).map((edge) => (
									<li
										key={edge.edge_id}
										className="text-[10px] text-slate-300"
										data-qid={`battle:adaptive-lineage:canonical-edge:${edge.edge_id}`}
										data-edge-id={edge.edge_id}
										data-parent-lane-id={edge.parent_lane_id}
										data-child-lane-id={edge.child_lane_id}
									>
										<span className="font-mono text-slate-400">{edge.parent_lane_id}→{edge.child_lane_id}</span>
										<span className="text-slate-500"> · {receiptLabel(edge.authorized_receipt_ref)}</span>
									</li>
								))}
							</ul>
						</div>
					);
				})}
			</div>
			<div className="mt-2 text-[10px] text-slate-500" data-qid="battle:adaptive-lineage:honesty">
				Loaded receipt fixture source only · does not prove live execution.
			</div>
		</section>
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
