interface RegisteredAction {
  app: string;
  action: string;
  label: string;
  description: string;
}

declare global {
  interface Window {
    __battleRegisteredActions?: Record<string, RegisteredAction>;
  }
}

export function useRegisterAction(qid: string, action: RegisteredAction): void {
  window.__battleRegisteredActions = window.__battleRegisteredActions ?? {};
  window.__battleRegisteredActions[qid] = action;
}
