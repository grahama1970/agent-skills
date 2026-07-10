import { useMemo, useState } from "react";
import { Badge } from "../ui/badge";
import type { MethodGroupView, ProofCardViewModel } from "../lib/battle-proof-card-view-model";

type Filter = "all" | "selected" | "deferred";

export function CandidateMethodsPanel({ groups }: { groups: ProofCardViewModel["methodGroups"] }) {
	const [filter, setFilter] = useState<Filter>("all");
	const [expanded, setExpanded] = useState<string | null>(null);

	const visible = useMemo(() => {
		if (filter === "all") return groups.filter((group) => group.methods.length > 0);
		if (filter === "selected") return groups.filter((group) => group.id === "selected");
		return groups.filter((group) => group.id === "deferred");
	}, [filter, groups]);

	return (
		<section className="battle-proof-panel" data-qid="battle:proof-card:methods">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="battle-label">Candidate methods</div>
				<div className="flex gap-1" role="group" aria-label="Filter methods">
					{(["all", "selected", "deferred"] as Filter[]).map((value) => (
						<button
							key={value}
							type="button"
							className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] ${
								filter === value ? "border-battle-purple/40 bg-battle-purple/15 text-violet-200" : "border-white/10 text-slate-500"
							}`}
							aria-pressed={filter === value}
							onClick={() => setFilter(value)}
						>
							{value}
						</button>
					))}
				</div>
			</div>
			<div className="mt-3 space-y-4">
				{visible.map((group) => (
					<MethodGroup key={group.id} group={group} expanded={expanded} setExpanded={setExpanded} />
				))}
			</div>
		</section>
	);
}

function MethodGroup({
	group,
	expanded,
	setExpanded,
}: {
	group: MethodGroupView;
	expanded: string | null;
	setExpanded: (id: string | null) => void;
}) {
	if (!group.methods.length) return null;
	return (
		<div data-battle-method-group={group.id}>
			<div className="mb-2 text-[11px] font-black uppercase tracking-[0.1em] text-slate-500">{group.label}</div>
			<div className="space-y-2">
				{group.methods.map((method) => {
					const open = expanded === method.method_id;
					return (
						<div key={method.method_id} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2" data-battle-method-id={method.method_id}>
							<button type="button" className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setExpanded(open ? null : method.method_id)} aria-expanded={open}>
								<span className="min-w-0">
									<span className="block font-semibold text-slate-100">{method.name}</span>
									<span className="mt-1 block text-xs text-slate-500">
										{[method.complexity, method.access_mode, method.technique_class].filter(Boolean).join(" · ") || "not emitted"}
									</span>
								</span>
								<Badge variant={group.id === "deferred" ? "yellow" : method.inherited ? "blue" : "purple"}>
									{group.id === "deferred" ? "deferred" : method.inherited ? "inherited" : "selected"}
								</Badge>
							</button>
							{open ? (
								<div className="mt-2 space-y-1 text-xs leading-5 text-slate-400">
									<div>
										<span className="battle-label mr-2">method id</span>
										<span className="font-mono text-slate-300">{method.method_id}</span>
									</div>
									<div>
										<span className="battle-label mr-2">source</span>
										{method.source ?? "not emitted"}
									</div>
									<div>
										<span className="battle-label mr-2">usefulness</span>
										{method.expected_usefulness ?? "not emitted"}
									</div>
									<div>
										<span className="battle-label mr-2">rationale</span>
										{method.rationale ?? "not emitted"}
									</div>
									<div>
										<span className="battle-label mr-2">risks</span>
										{(method.known_risks ?? []).join(" · ") || "not emitted"}
									</div>
									<div>
										<span className="battle-label mr-2">evidence</span>
										{(method.evidence_refs ?? []).join(", ") || "not emitted"}
									</div>
								</div>
							) : null}
						</div>
					);
				})}
			</div>
		</div>
	);
}
