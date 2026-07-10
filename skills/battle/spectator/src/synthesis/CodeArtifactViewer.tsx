import type { SynthesisViewModel } from "../lib/battle-synthesis-view-model";

export function CodeArtifactViewer({
	model,
	focused,
}: {
	model: SynthesisViewModel["specimen"];
	focused?: boolean;
}) {
	const previewText = model.previewLines.join("\n");
	return (
		<section className="battle-proof-panel" data-qid="battle:synthesis:code" data-focused={focused ? "true" : undefined}>
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="battle-label">Code artifact (read-only preview)</div>
				<div className="font-mono text-[11px] text-slate-500">
					{model.label} · {model.language}
				</div>
			</div>
			<div className="battle-synthesis-code-meta">
				<span data-qid="battle:synthesis:code:specimen-id">specimen: {model.id}</span>
				<span data-qid="battle:synthesis:code:line-count">
					preview lines: {model.previewLines.length} / {model.lineCount}
					{model.truncated ? " (truncated)" : ""}
				</span>
			</div>
			<pre className="battle-synthesis-code" data-qid="battle:synthesis:code:preview" tabIndex={0} aria-label="Read-only specimen code preview">
				{previewText}
			</pre>
			<div className="battle-proof-notice mt-3" data-qid="battle:synthesis:code:readonly-notice">
				Read-only escaped preview from specimen.code_preview.lines. No compile, run, or execute controls.
			</div>
		</section>
	);
}
