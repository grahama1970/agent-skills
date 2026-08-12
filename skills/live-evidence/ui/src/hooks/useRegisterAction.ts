import { useEffect, useRef } from "react";

import type { ActionDefinition } from "@/types";

const pending: ActionDefinition[] = [];
const queued = new Set<string>();
const flushed = new Set<string>();
let timer: ReturnType<typeof setTimeout> | null = null;

function keyOf(action: ActionDefinition): string {
  return `${action.app}::${action.action}::${action.element_id}`;
}

function flush() {
  if (pending.length === 0) return;
  const batch = pending.splice(0, 200);
  fetch("/api/actions/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actions: batch }),
  })
    .then((response) => {
      if (!response.ok) throw new Error(`action registration failed: ${response.status}`);
      batch.forEach((action) => {
        queued.delete(keyOf(action));
        flushed.add(keyOf(action));
      });
    })
    .catch(() => {
      batch.forEach((action) => queued.delete(keyOf(action)));
    })
    .finally(() => {
      timer = null;
      if (pending.length > 0) timer = setTimeout(flush, 100);
    });
}

export function useRegisterAction(action: ActionDefinition) {
  const registered = useRef(false);
  const key = keyOf(action);

  useEffect(() => {
    if (registered.current || queued.has(key) || flushed.has(key)) return;
    registered.current = true;
    pending.push(action);
    queued.add(key);
    if (timer) clearTimeout(timer);
    timer = setTimeout(flush, 350);
  }, [key]);
}
