import { createRoot } from "react-dom/client";
import { BattleSpectatorRoot } from "./BattleActionRegistrar";
import { BattleSpectatorArena } from "./BattleSpectatorArena";

createRoot(document.getElementById("root")!).render(
	<BattleSpectatorRoot>
		<BattleSpectatorArena />
	</BattleSpectatorRoot>,
);
