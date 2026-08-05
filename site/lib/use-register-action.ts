'use client';

import { useEffect } from 'react';

export interface RegisterActionMeta {
  app: string;
  action: string;
  label: string;
  description: string;
}

/**
 * Static-build adapter for the best-practices-react `useRegisterAction` rule.
 *
 * The canonical hook registers actions to the private ArangoDB `app_actions`
 * collection. This public static site has no path to that runtime, so the
 * hook keeps the same call signature and action-ID discipline but only
 * forwards to a runtime endpoint when one is injected at
 * `window.__APP_ACTIONS_ENDPOINT__` (never on the public build).
 * See site/CLAUDE.md for the documented exception.
 */
export function useRegisterAction(qid: string, meta: RegisterActionMeta) {
  useEffect(() => {
    const endpoint = (window as unknown as Record<string, unknown>)
      .__APP_ACTIONS_ENDPOINT__;
    if (typeof endpoint !== 'string') return;
    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ qid, ...meta }),
    }).catch(() => {
      // Registration is best-effort telemetry; the UI never depends on it.
    });
  }, [qid, meta.app, meta.action, meta.label, meta.description]);
}
