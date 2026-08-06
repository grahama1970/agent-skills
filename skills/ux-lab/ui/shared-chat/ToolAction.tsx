/**
 * ToolAction — Collapsible muted line showing "Ran /skill-name".
 * Shared across Embry Terminal + SPARTA Explorer chat UIs.
 */
import { memo, useState } from "react";
import { useRegisterAction } from "./_support/useRegisterAction";

interface ToolActionProps {
	label: string;
	qid: string;
}

export const ToolAction = memo(function ToolAction({ label, qid }: ToolActionProps) {
	const [expanded, setExpanded] = useState(false);
	useRegisterAction(qid, { app: "shared-chat", action: "TOOL_ACTION_TOGGLE", label, description: `Toggle tool action: ${label}` });
	return (
		<button
			data-qid={qid}
			data-qs-action="TOOL_ACTION_TOGGLE"
			title={`${label} — click to ${expanded ? "collapse" : "expand"} details`}
			onClick={() => setExpanded((v) => !v)}
			style={{
				display: "flex",
				alignItems: "center",
				gap: 6,
				fontSize: 13,
				color: "#94a3b8",
				background: "none",
				border: "none",
				cursor: "pointer",
				padding: "8px 4px",
				marginBottom: 4,
				minHeight: 44,
				fontFamily: "var(--font-ui)",
				transition: "color 0.15s",
			}}
		>
			{label}
			<svg
				width={12}
				height={12}
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				strokeWidth={2}
				style={{
					color: "#64748b",
					transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
					transition: "transform 0.15s",
				}}
			>
				<polyline points="6 9 12 15 18 9" />
			</svg>
		</button>
	);
});
