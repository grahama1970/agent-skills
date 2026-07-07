import { createContext, type ReactNode, useMemo, useRef } from "react";
import { BATTLE_SPECTATOR_APP_ID } from "./lib/battle-spectator-app";

export type BattleRegisteredAction = {
	app: string;
	action: string;
	label: string;
	description: string;
	params?: Record<string, unknown>;
	tags?: string[];
};

export type BattleActionRegistrar = {
	register(qid: string, action: BattleRegisteredAction): void;
	unregister(qid: string): void;
};

export const BattleActionRegistrarContext = createContext<BattleActionRegistrar | null>(null);
export const BattleSpectatorAppIdContext = createContext<string>(BATTLE_SPECTATOR_APP_ID);

type Props = {
	children: ReactNode;
	appId?: string;
	registerAction?: (qid: string, action: BattleRegisteredAction) => void | (() => void);
};

export function BattleSpectatorRoot({ children, appId = BATTLE_SPECTATOR_APP_ID, registerAction }: Props) {
	const cleanupsRef = useRef(new Map<string, () => void>());

	const registrar = useMemo<BattleActionRegistrar>(
		() => ({
			register(qid, action) {
				cleanupsRef.current.get(qid)?.();
				if (registerAction) {
					const cleanup = registerAction(qid, action);
					if (typeof cleanup === "function") cleanupsRef.current.set(qid, cleanup);
					else cleanupsRef.current.delete(qid);
				}
			},
			unregister(qid) {
				cleanupsRef.current.get(qid)?.();
				cleanupsRef.current.delete(qid);
			},
		}),
		[registerAction],
	);

	return (
		<BattleSpectatorAppIdContext.Provider value={appId}>
			<BattleActionRegistrarContext.Provider value={registrar}>{children}</BattleActionRegistrarContext.Provider>
		</BattleSpectatorAppIdContext.Provider>
	);
}
