import { createContext, type ReactNode, useMemo, useRef } from "react";

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

type Props = {
	children: ReactNode;
	registerAction?: (qid: string, action: BattleRegisteredAction) => void | (() => void);
};

export function BattleSpectatorRoot({ children, registerAction }: Props) {
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

	return <BattleActionRegistrarContext.Provider value={registrar}>{children}</BattleActionRegistrarContext.Provider>;
}
