import { Badge } from "../ui/badge";
import type { CompileViewModel } from "../lib/battle-compile-view-model";

function statusVariant(status: string) {
	const upper = status.toUpperCase();
	if (upper === "PASSED") return "green" as const;
	if (upper === "FAILED") return "red" as const;
	return "default" as const;
}

export function SpecimenVersionTimeline({
	versions,
	focused,
}: {
	versions: CompileViewModel["versions"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:compile:versions" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Specimen version timeline</div>
			<div className="mt-3 grid gap-2">
				{versions.map((version) => (
					<div
						key={version.id}
						className="battle-compile-version"
						data-selected={version.selected ? "true" : undefined}
						data-qid={`battle:compile:version:${version.id}`}
					>
						<div className="flex flex-wrap items-center justify-between gap-2">
							<div>
								<div className="text-sm font-semibold text-slate-100">
									{version.id} · {version.role.replace(/_/g, " ")}
								</div>
								<div className="mt-0.5 font-mono text-[11px] text-slate-500">{version.label}</div>
							</div>
							<div className="flex items-center gap-2">
								{version.selected ? <Badge variant="purple">selected</Badge> : null}
								<Badge variant={statusVariant(version.compileStatus)}>{version.compileStatus}</Badge>
							</div>
						</div>
						<div className="mt-2 grid gap-1 text-xs text-slate-400">
							<div>
								<span className="battle-label mr-2">sha256</span>
								<span className="break-all font-mono text-[11px] text-slate-200">{version.sha256}</span>
							</div>
							<div>
								<span className="battle-label mr-2">bytes</span>
								<span className="font-mono text-slate-200">{version.bytes}</span>
								<span className="battle-label ml-3 mr-2">compile attempted</span>
								<span className="text-slate-200">{version.attempted ? "yes" : "no"}</span>
							</div>
							{version.sourceVersionId ? (
								<div>
									<span className="battle-label mr-2">source version</span>
									<span className="font-mono text-slate-200">{version.sourceVersionId}</span>
								</div>
							) : null}
						</div>
					</div>
				))}
			</div>
		</section>
	);
}
