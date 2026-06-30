import type { ReactNode } from "react";
import { X } from "lucide-react";
import { EMBRY } from "../common/EmbryStyle";

export interface SharedRightPaneTab {
	id: string;
	label: string;
}

interface SharedRightPaneProps {
	title: string;
	subtitle?: string;
	tabs: SharedRightPaneTab[];
	activeTab: string;
	onTabChange: (tab: string) => void;
	onClose: () => void;
	actions?: ReactNode;
	mode?: "overlay" | "docked";
	width?: number;
	children: ReactNode;
}

export function SharedRightPane({
	title,
	subtitle,
	tabs,
	activeTab,
	onTabChange,
	onClose,
	actions,
	mode = "overlay",
	width = 480,
	children,
}: SharedRightPaneProps) {
	const isDocked = mode === "docked";

	return (
		<div
			style={{
				position: isDocked ? "relative" : "fixed",
				top: isDocked ? undefined : 0,
				right: isDocked ? undefined : 0,
				width,
				height: isDocked ? "auto" : "100%",
				flexShrink: 0,
				backgroundColor: EMBRY.bgDeep,
				borderLeft: `1px solid ${EMBRY.border}`,
				boxShadow: isDocked ? "none" : "-8px 0 32px rgba(0,0,0,0.45)",
				zIndex: 1100,
				display: "flex",
				flexDirection: "column",
			}}
		>
			<div
				style={{
					padding: "12px 16px",
					borderBottom: `1px solid ${EMBRY.border}`,
					display: "flex",
					alignItems: "flex-start",
					justifyContent: "space-between",
					gap: 12,
				}}
			>
				<div style={{ minWidth: 0 }}>
					<div style={{ fontSize: 12, fontWeight: 800, color: EMBRY.white }}>{title}</div>
					{subtitle && (
						<div
							style={{
								fontSize: 10,
								color: EMBRY.dim,
								marginTop: 4,
								whiteSpace: "nowrap",
								overflow: "hidden",
								textOverflow: "ellipsis",
							}}
						>
							{subtitle}
						</div>
					)}
				</div>
				<button aria-label="Action"
					data-qid="shared-right-pane:close"
					data-qs-action="SHARED_RIGHT_PANE_CLOSE"
					title="Close detail pane"
					onClick={onClose}
					style={{
						background: "none",
						border: "none",
						color: EMBRY.dim,
						cursor: "pointer",
						padding: 0,
						width: 44,
						minWidth: 44,
						minHeight: 44,
						display: "flex",
						alignItems: "center",
						justifyContent: "center",
						flexShrink: 0,
					}}
				>
					<X size={16} />
				</button>
			</div>

			<div
				style={{
					padding: "10px 16px 0",
					display: "flex",
					flexDirection: "column",
					gap: 10,
					borderBottom: `1px solid ${EMBRY.border}`,
				}}
			>
				{actions && <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{actions}</div>}
				<div style={{ display: "flex", gap: 8 }}>
					{tabs.map((tab) => (
						<button aria-label="Action"
							key={tab.id}
							data-qid={`shared-right-pane:tab:${tab.id}`}
							data-qs-action={`SHARED_RIGHT_PANE_TAB_${String(tab.id).replace(/[^a-z0-9]+/gi, "_").toUpperCase()}`}
							title={`Show ${tab.label}`}
							onClick={() => onTabChange(tab.id)}
							style={{
								minWidth: 44,
								minHeight: 44,
								padding: "8px 10px",
								border: "none",
								borderBottom: activeTab === tab.id ? `2px solid ${EMBRY.blue}` : "2px solid transparent",
								background: "none",
								color: activeTab === tab.id ? EMBRY.blue : EMBRY.dim,
								fontSize: 10,
								fontWeight: 800,
								textTransform: "uppercase",
								letterSpacing: "0.08em",
								cursor: "pointer",
							}}
						>
							{tab.label}
						</button>
					))}
				</div>
			</div>

			<div style={{ flex: 1, overflowY: "auto", padding: 16 }}>{children}</div>
		</div>
	);
}
