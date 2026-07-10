import { useState } from "react";
import { Badge } from "../ui/badge";
import type { ProofCardViewModel } from "../lib/battle-proof-card-view-model";

export function ResearchEvidencePanel({
	model,
	focused,
}: {
	model: ProofCardViewModel["research"];
	focused?: boolean;
}) {
	const [expanded, setExpanded] = useState<string | null>(null);

	return (
		<section className="battle-proof-panel" data-qid="battle:proof-card:research" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Research evidence</div>
			<div className="mt-2 grid gap-1 text-xs text-slate-400">
				<div>
					<span className="battle-label mr-2">Research mode</span>
					<span className="text-slate-200">{model.method === "manual" ? "Manual source packet" : model.method}</span>
				</div>
				<div data-qid="battle:proof-card:research:external-tool">
					<span className="battle-label mr-2">External research tool called</span>
					<span className="text-slate-200">{model.externalToolCalled ? "Yes" : "No"}</span>
				</div>
				<div data-qid="battle:proof-card:research:provider-live">
					<span className="battle-label mr-2">Provider/model called</span>
					<span className="text-slate-200">{model.providerLive ? "Yes" : "No"}</span>
				</div>
				<div>
					<span className="battle-label mr-2">Review required</span>
					<span className="text-slate-200">{model.reviewRequired ? "Yes" : "No"}</span>
				</div>
				<div>
					<span className="battle-label mr-2">Sources</span>
					<span className="text-slate-200">{model.sourceCount}</span>
				</div>
			</div>
			<p className="mt-3 text-sm leading-6 text-slate-300">{model.query}</p>
			<div className="battle-proof-notice mt-3" role="note">
				{model.designInputNotice}
			</div>
			<div className="mt-3 space-y-2">
				{model.sources.map((source) => {
					const open = expanded === source.source_id;
					return (
						<div key={source.source_id} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
							<button
								type="button"
								className="flex w-full items-start justify-between gap-3 text-left"
								onClick={() => setExpanded(open ? null : source.source_id)}
								aria-expanded={open}
							>
								<span className="min-w-0">
									<span className="block font-semibold text-slate-100">{source.title}</span>
									<span className="mt-1 block text-xs text-slate-500">
										{source.source_type ?? "not emitted"} · {source.method ?? "not emitted"} · relevance {source.relevance ?? "not emitted"}
									</span>
								</span>
								<Badge variant="blue">{open ? "Hide" : "Details"}</Badge>
							</button>
							{open ? (
								<div className="mt-2 space-y-2 text-xs leading-5 text-slate-400">
									<div>
										<span className="battle-label mr-2">claims supported</span>
										{(source.claims_supported ?? []).join(" · ") || "not emitted"}
									</div>
									<div>
										<span className="battle-label mr-2">limitations</span>
										{(source.limitations ?? []).join(" · ") || "not emitted"}
									</div>
									{source.url ? (
										<a
											className="inline-flex text-battle-blue underline-offset-2 hover:underline"
											href={source.url}
											target="_blank"
											rel="noreferrer"
											aria-label={`Open external source ${source.title}`}
										>
											Open external source
										</a>
									) : null}
								</div>
							) : null}
						</div>
					);
				})}
			</div>
		</section>
	);
}
