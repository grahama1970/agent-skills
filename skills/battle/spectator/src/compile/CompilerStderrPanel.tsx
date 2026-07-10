import type { CompileViewModel } from "../lib/battle-compile-view-model";

export function CompilerStderrPanel({
	model,
	focused,
}: {
	model: CompileViewModel["compile"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:compile:stderr" data-focused={focused ? "true" : undefined}>
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="battle-label">Compiler stderr summary</div>
				<div className="text-[11px] uppercase tracking-[0.08em] text-slate-500">
					{model.stderrAvailable ? (model.stderrRedacted ? "redacted" : "available") : "not emitted"}
				</div>
			</div>
			{model.stderrAvailable && model.stderrLines.length ? (
				<pre className="battle-compile-stderr" data-qid="battle:compile:stderr:preview" tabIndex={0} aria-label="Compiler stderr summary">
					{model.stderrLines.join("\n")}
				</pre>
			) : (
				<div className="mt-3 text-sm text-slate-500">No stderr summary emitted.</div>
			)}
		</section>
	);
}
