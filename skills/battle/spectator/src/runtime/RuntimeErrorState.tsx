import type { RuntimeLoadError } from "../lib/battle-runtime-types";

export function RuntimeErrorState({ error }: { error: RuntimeLoadError }) {
	return (
		<div className="grid h-full place-items-center p-6 text-center" data-qid="battle:runtime:error">
			<div>
				<div className="text-lg font-black tracking-wide text-battle-red">{error.title}</div>
				<div className="mt-2 max-w-xl text-sm leading-6 text-slate-300">{error.detail}</div>
			</div>
		</div>
	);
}
