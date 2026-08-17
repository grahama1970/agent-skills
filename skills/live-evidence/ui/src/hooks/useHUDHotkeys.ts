import { useCallback, useEffect, useRef } from "react";

export type HotkeyHandler = (event: KeyboardEvent) => void;

export interface HotkeyBinding {
  key: string;
  handler: HotkeyHandler;
  preventDefault?: boolean;
  allowInInputs?: boolean;
}

interface UseHUDHotkeysOptions {
  enabled?: boolean;
}

function isFormTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target.isContentEditable;
}

function matchesKeyCombination(event: KeyboardEvent, combo: string): boolean {
  const parts = combo.split("+").map((part) => part.trim());
  const mainKey = parts.at(-1) ?? combo;
  const eventKey = event.key === " " ? "Space" : event.key;

  if (parts.includes("Shift") !== event.shiftKey) return false;
  if (parts.includes("Ctrl") !== event.ctrlKey) return false;
  if (parts.includes("Alt") !== event.altKey) return false;
  if ((parts.includes("Cmd") || parts.includes("Meta")) !== event.metaKey) return false;

  return eventKey.toLowerCase() === mainKey.toLowerCase() || event.code.toLowerCase() === mainKey.toLowerCase();
}

export function useHUDHotkeys(bindings: HotkeyBinding[], options: UseHUDHotkeysOptions = {}) {
  const { enabled = true } = options;
  const bindingsRef = useRef(bindings);

  useEffect(() => {
    bindingsRef.current = bindings;
  }, [bindings]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!enabled) return;
      const inputFocused = isFormTarget(document.activeElement);

      for (const binding of bindingsRef.current) {
        if (inputFocused && !binding.allowInInputs) continue;
        if (!matchesKeyCombination(event, binding.key)) continue;
        if (binding.preventDefault ?? true) event.preventDefault();
        binding.handler(event);
        break;
      }
    },
    [enabled],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}
