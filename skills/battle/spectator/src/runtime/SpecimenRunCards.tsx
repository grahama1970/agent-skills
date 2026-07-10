import { useState } from "react";
import { Badge } from "../ui/badge";
import type { RuntimeRunView, RuntimeViewModel } from "../lib/battle-runtime-view-model";

function statusVariant(tone: RuntimeRunView["tone"]) {
	if (tone === "green") return "green" as const;
	if (tone === "red") return "red" as const;
	if (tone === "amber") return "yellow" as const;
	if (tone === "blue") return "blue" as const;
	return "default" as const;
}

export function SpecimenRunCards({
	runs,
	selectedRunId,
	focused,
}: {
	runs: RuntimeViewModel["runs"];
	selectedRunId: string;
	focused?: boolean;
}) {
	const [expandedId, setExpandedId] = useState<string | null>(selectedRunId);

	return (
		<section className="battle-proof-panel" data-qid="battle:runtime:runs" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Specimen runs</div>
			<div className="mt-3 grid gap-2">
				{runs.map((run) => {
					const expanded = expandedId === run.id;
					return (
						<div
							key={run.id}
							className="battle-runtime-run"
							data-selected={run.id === selectedRunId ? "true" : undefined}
							data-qid={`battle:runtime:run:${run.id}`}
						>
							<button
								type="button"
								className="flex w-full flex-wrap items-center justify-between gap-2 text-left"
								onClick={() => setExpandedId((value) => (value === run.id ? null : run.id))}
							>
								<div>
									<div className="text-sm font-semibold text-slate-100">{run.id}</div>
									<div className="mt-0.5 font-mono text-[11px] text-slate-500">{run.rawStatus}</div>
								</div>
								<div className="flex items-center gap-2">
									{run.id === selectedRunId ? <Badge variant="purple">best</Badge> : null}
									<Badge variant={statusVariant(run.tone)}>{run.runtimeStatus}</Badge>
								</div>
							</button>
							<div className="mt-2 grid gap-1 text-xs text-slate-400 md:grid-cols-2">
								<div>
									<span className="battle-label mr-2">exit</span>
									<span className="font-mono text-slate-200">{run.exitCode}</span>
									<span className="battle-label ml-3 mr-2">compile_ok</span>
									<span className="text-slate-200">{run.compileOk ? "yes" : "no"}</span>
									<span className="battle-label ml-3 mr-2">runtime_ok</span>
									<span className="text-slate-200">{run.runtimeOk ? "yes" : "no"}</span>
								</div>
								<div data-qid={`battle:runtime:run:${run.id}:target`}>
									<span className="battle-label mr-2">target</span>
									<span className="text-slate-200">{run.targetStatus}</span>
									{run.targetObserved ? (
										<span className="ml-2 font-mono text-[11px] text-slate-500">{run.targetEntrypoint}</span>
									) : null}
								</div>
							</div>
							{expanded ? (
								<div className="mt-3 grid gap-3 xl:grid-cols-2">
									<div>
										<div className="battle-label mb-1">stdout summary</div>
										<pre className="battle-runtime-io" data-qid={`battle:runtime:run:${run.id}:stdout`}>
											{run.stdoutAvailable && run.stdoutLines.length ? run.stdoutLines.join("\n") : "not emitted"}
										</pre>
									</div>
									<div>
										<div className="battle-label mb-1">stderr summary</div>
										<pre className="battle-runtime-io" data-qid={`battle:runtime:run:${run.id}:stderr`}>
											{run.stderrAvailable && run.stderrLines.length ? run.stderrLines.join("\n") : "not emitted"}
										</pre>
									</div>
									{run.doesNotProve.length ? (
										<div className="xl:col-span-2" data-qid={`battle:runtime:run:${run.id}:does-not-prove`}>
											<div className="battle-label mb-1">Does not prove</div>
											<ul className="space-y-1 text-sm text-slate-300">
												{run.doesNotProve.map((item) => (
													<li key={item}>{item}</li>
												))}
											</ul>
										</div>
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
