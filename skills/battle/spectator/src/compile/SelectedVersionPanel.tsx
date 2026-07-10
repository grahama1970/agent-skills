import { Badge } from "../ui/badge";
import type { CompileViewModel } from "../lib/battle-compile-view-model";

function statusVariant(status: string) {
	const upper = status.toUpperCase();
	if (upper === "PASSED") return "green" as const;
	if (upper === "FAILED") return "red" as const;
	return "default" as const;
}

export function SelectedVersionPanel({
	model,
	focused,
}: {
	model: CompileViewModel["selectedVersion"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:compile:selected" data-focused={focused ? "true" : undefined}>
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="battle-label">Selected version</div>
				<Badge variant={statusVariant(model.compileStatus)}>{model.compileStatus}</Badge>
			</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300">
				<div data-qid="battle:compile:selected:id">
					<span className="battle-label mr-2">version</span>
					<span className="font-mono text-slate-100">{model.id}</span>
				</div>
				<div>
					<span className="battle-label mr-2">sha256</span>
					<span className="break-all font-mono text-[11px] text-slate-200">{model.sha256}</span>
				</div>
				<div data-qid="battle:compile:selected:flags">
					<span className="battle-label mr-2">failed</span>
					<span className="text-slate-100">{model.failed ? "yes" : "no"}</span>
					<span className="battle-label ml-3 mr-2">passed</span>
					<span className="text-slate-100">{model.passed ? "yes" : "no"}</span>
				</div>
			</div>
			<div className="battle-proof-notice mt-3">Compile pass is never rendered as runnable.</div>
		</section>
	);
}
