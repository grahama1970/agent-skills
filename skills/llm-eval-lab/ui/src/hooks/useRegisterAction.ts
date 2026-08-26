import { useEffect, useRef } from "react";

// best-practices-react: register interactive actions so agents/voice can resolve
// intent -> action id -> DOM click. Batches to /api/actions/register (the control
// server appends to a JSONL ledger); failures are non-fatal.
export interface ActionDefinition {
  app: string;
  action: string;
  element_id: string;
  label: string;
}

const pending: ActionDefinition[] = [];
const seen = new Set<string>();
let timer: ReturnType<typeof setTimeout> | null = null;
const keyOf = (a: ActionDefinition) => `${a.app}::${a.action}::${a.element_id}`;

function flush() {
  if (pending.length === 0) return;
  const batch = pending.splice(0, 200);
  fetch("/api/actions/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actions: batch }),
  }).catch(() => {}).finally(() => { timer = null; });
}

export function useRegisterAction(action: ActionDefinition) {
  const key = keyOf(action);
  const ref = useRef<string | null>(null);
  useEffect(() => {
    if (ref.current === key || seen.has(key)) return;
    ref.current = key;
    seen.add(key);
    pending.push(action);
    if (timer) clearTimeout(timer);
    timer = setTimeout(flush, 300);
  }, [key]);
}
