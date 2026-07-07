import { useContext, useEffect, useMemo } from "react";
import { BattleActionRegistrarContext, BattleSpectatorAppIdContext, type BattleRegisteredAction } from "../BattleActionRegistrar";
import { BATTLE_SPECTATOR_APP_ID } from "../lib/battle-spectator-app";

export type { BattleRegisteredAction };

export function useRegisterAction(qid: string, action: Omit<BattleRegisteredAction, "app"> & { app?: string }): void {
	const registrar = useContext(BattleActionRegistrarContext);
	const appId = useContext(BattleSpectatorAppIdContext) ?? BATTLE_SPECTATOR_APP_ID;
	const resolved = useMemo<BattleRegisteredAction>(() => ({ ...action, app: action.app ?? appId }), [action, appId]);

	useEffect(() => {
		if (registrar) {
			registrar.register(qid, resolved);
			return () => registrar.unregister(qid);
		}

		window.__battleRegisteredActions = window.__battleRegisteredActions ?? {};
		window.__battleRegisteredActions[qid] = resolved;
		return () => {
			if (window.__battleRegisteredActions) delete window.__battleRegisteredActions[qid];
		};
	}, [qid, registrar, resolved]);
}

declare global {
	interface Window {
		__battleRegisteredActions?: Record<string, BattleRegisteredAction>;
	}
}
