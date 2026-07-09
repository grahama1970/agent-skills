import { useEffect } from "react";
import type { HungerGamesDeathCard } from "./lib/battle-hunger-games-notifications";
import "./battle-hunger-games-death.css";

type Props = {
	card: HungerGamesDeathCard | null;
	onDismiss: () => void;
	durationMs?: number;
};

export function BattleHungerGamesDeathAnnouncement({ card, onDismiss, durationMs = 5200 }: Props) {
	useEffect(() => {
		if (!card) return;
		const timer = window.setTimeout(onDismiss, durationMs);
		return () => window.clearTimeout(timer);
	}, [card, durationMs, onDismiss]);

	if (!card) return null;

	return (
		<div
			className="battle-hg-death-notification"
			data-qid="battle:death-announcement"
			data-testid="battle-hunger-games-death-card"
			role="status"
			aria-live="assertive"
		>
			<div className="battle-hg-death-card">
				<div className="battle-hg-death-portrait-col">
					<div className="battle-hg-death-portrait-frame" aria-hidden="true">
						<img className="battle-hg-death-portrait" src={card.portraitSrc} alt="" />
						<div className="battle-hg-death-portrait-scan" />
						<div className="battle-hg-death-portrait-glow" />
					</div>
					<div className="battle-hg-death-nameplate">
						<span className="battle-hg-death-name">{card.tributeName}</span>
					</div>
				</div>
				<div className="battle-hg-death-info-panel">
					<div className="battle-hg-death-info-label">Virus Information</div>
					<div className="battle-hg-death-info-body">{card.tributeInfo}</div>
				</div>
			</div>
		</div>
	);
}
