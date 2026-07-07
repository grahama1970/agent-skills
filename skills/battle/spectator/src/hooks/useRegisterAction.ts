import { useContext, useEffect } from "react";
import { BattleActionRegistrarContext, type BattleRegisteredAction } from "../BattleActionRegistrar";

export type { BattleRegisteredAction };

export function useRegisterAction(qid: string, action: BattleRegisteredAction): void {
	const registrar = useContext(BattleActionRegistrarContext);

	useEffect(() => {
		if (registrar) {
			registrar.register(qid, action);
			return () => registrar.unregister(qid);
		}

		window.__battleRegisteredActions = window.__battleRegisteredActions ?? {};
		window.__battleRegisteredActions[qid] = action;
		return () => {
			if (window.__battleRegisteredActions) delete window.__battleRegisteredActions[qid];
		};
	}, [action, qid, registrar]);
}

declare global {
	interface Window {
		__battleRegisteredActions?: Record<string, BattleRegisteredAction>;
	}
}
