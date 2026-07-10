import { Badge } from "../ui/badge";
import type { CompileViewModel } from "../lib/battle-compile-view-model";

function statusVariant(status: string | null | undefined) {
	const upper = (status ?? "").toUpperCase();
	if (upper === "PASS") return "green" as const;
	if (upper === "BLOCKED") return "yellow" as const;
	if (upper === "FAIL") return "red" as const;
	return "default" as const;
}

export function CompileReceiptPanel({
	receipts,
	focused,
}: {
	receipts: CompileViewModel["receipts"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:compile:receipts" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Receipt references</div>
			<div className="mt-2 space-y-1">
				{receipts.map((ref) => (
					<div key={ref.id} className="grid grid-cols-[1fr_auto_auto] items-center gap-2 rounded border border-white/10 bg-black/20 px-2 py-1.5 text-xs">
						<button
							type="button"
							className="truncate text-left font-mono text-slate-200 hover:text-white"
							title="Copy receipt id"
							onClick={() => void navigator.clipboard?.writeText(ref.id)}
						>
							{ref.id}
						</button>
						<span className="truncate text-slate-500">{ref.schema ?? "not emitted"}</span>
						<Badge variant={statusVariant(ref.status)}>{ref.status ?? "not emitted"}</Badge>
					</div>
				))}
			</div>
		</section>
	);
}
