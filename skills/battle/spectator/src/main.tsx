import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { BattleSpectatorRoot } from "./BattleActionRegistrar";
import { BattleSpectatorArena } from "./BattleSpectatorArena";
import "./standalone.css";

const root = document.getElementById("root");

if (!root) {
	throw new Error("Battle Spectator root element was not found.");
}

createRoot(root).render(
	<StrictMode>
		<BattleSpectatorRoot appId="battle-spectator-standalone">
			<BattleSpectatorArena />
		</BattleSpectatorRoot>
	</StrictMode>,
);
