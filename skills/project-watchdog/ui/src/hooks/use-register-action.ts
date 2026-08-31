import { useEffect } from 'react';

type RegisteredAction = {
  qid: string;
  action: string;
  title: string;
};

declare global {
  interface Window {
    __PROJECT_WATCHDOG_ACTIONS__?: RegisteredAction[];
  }
}

export function useRegisterAction(action: RegisteredAction) {
  useEffect(() => {
    const registry = window.__PROJECT_WATCHDOG_ACTIONS__ ?? [];
    window.__PROJECT_WATCHDOG_ACTIONS__ = registry.filter((entry) => entry.qid !== action.qid).concat(action);
    return () => {
      window.__PROJECT_WATCHDOG_ACTIONS__ = (window.__PROJECT_WATCHDOG_ACTIONS__ ?? []).filter(
        (entry) => entry.qid !== action.qid,
      );
    };
  }, [action.action, action.qid, action.title]);
}
