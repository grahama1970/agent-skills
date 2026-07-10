import type { RuntimeViewModel } from "../lib/battle-runtime-view-model";

export function DockerPolicyPanel({
	model,
	focused,
}: {
	model: RuntimeViewModel["docker"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:runtime:docker" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Docker policy</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300">
				<div data-qid="battle:runtime:docker:image">
					<span className="battle-label mr-2">image</span>
					<span className="font-mono text-slate-100">{model.image}</span>
				</div>
				<div data-qid="battle:runtime:docker:network">
					<span className="battle-label mr-2">network</span>
					<span className="font-mono text-slate-100">{model.network}</span>
				</div>
				<div data-qid="battle:runtime:docker:timeout">
					<span className="battle-label mr-2">timeout</span>
					<span className="font-mono text-slate-100">{model.timeoutSeconds}s</span>
				</div>
				<div>
					<span className="battle-label mr-2">user</span>
					<span className="font-mono text-slate-100">{model.user}</span>
				</div>
				<div>
					<span className="battle-label mr-2">cap-drop ALL</span>
					<span className="text-slate-100">{model.capDropAll ? "yes" : "no"}</span>
					<span className="battle-label ml-3 mr-2">no-new-privileges</span>
					<span className="text-slate-100">{model.noNewPrivileges ? "yes" : "no"}</span>
				</div>
			</div>
			{model.commandShape.length ? (
				<pre className="battle-runtime-io mt-3" data-qid="battle:runtime:docker:command">
					{model.commandShape.join(" ")}
				</pre>
			) : null}
		</section>
	);
}
