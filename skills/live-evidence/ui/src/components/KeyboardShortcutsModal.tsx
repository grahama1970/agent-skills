import { Command, Keyboard, X } from "lucide-react";
import { useEffect } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";

interface KeyboardShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ShortcutItem {
  keys: string[];
  description: string;
  category: "Navigation" | "Card Controls" | "Global";
}

const SHORTCUTS: ShortcutItem[] = [
  { keys: ["J", "↓"], description: "Select next question down the timeline", category: "Navigation" },
  { keys: ["K", "↑"], description: "Select previous question up the timeline", category: "Navigation" },
  { keys: ["Space"], description: "Flip active card (glance front ↔ full back)", category: "Card Controls" },
  { keys: ["P"], description: "Pin or unpin the active card", category: "Card Controls" },
  { keys: ["D", "Esc"], description: "Dismiss the active card", category: "Card Controls" },
  { keys: ["Ctrl+\\"], description: "Toggle the raw STT transcript drawer", category: "Global" },
  { keys: ["?"], description: "Toggle this shortcuts helper", category: "Global" },
];

export function KeyboardShortcutsModal({ isOpen, onClose }: KeyboardShortcutsModalProps) {
  useRegisterAction({
    element_id: "keyboard-shortcuts-close",
    app: "live-evidence",
    action: "close_shortcuts",
    label: "Close shortcuts",
    description: "Dismiss the keyboard shortcuts modal.",
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isOpen) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;
  const categories = [...new Set(SHORTCUTS.map((item) => item.category))];

  return (
    <div className="fixed inset-0 z-50 flex select-none items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="absolute inset-0" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg overflow-hidden rounded-2xl border-2 border-slate-800/90 bg-[#0e101a] font-sans text-slate-100 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800/80 bg-[#121424] px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-2 text-indigo-400">
              <Keyboard className="size-5" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-base font-bold leading-none text-white">HUD Shortcuts</h3>
              <p className="mt-1 text-xs text-slate-400">Single-key control for the live copilot</p>
            </div>
          </div>
          <button
            type="button"
            data-qid="keyboard-shortcuts-close"
            data-qs-action="close_shortcuts"
            onClick={onClose}
            className="cursor-pointer rounded-lg border border-slate-800 bg-slate-900 p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-100"
            title="Close keyboard shortcuts"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
        <div className="max-h-[70vh] space-y-6 overflow-y-auto p-6">
          {categories.map((category) => (
            <div key={category} className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-widest text-indigo-400">{category}</h4>
              <div className="space-y-2">
                {SHORTCUTS.filter((item) => item.category === category).map((shortcut) => (
                  <div
                    key={shortcut.description}
                    className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-slate-900/60 p-3 transition-colors hover:border-slate-700"
                  >
                    <span className="text-sm font-medium text-slate-200">{shortcut.description}</span>
                    <div className="flex items-center gap-1.5 font-mono">
                      {shortcut.keys.map((key) => (
                        <kbd
                          key={key}
                          className="rounded-md border border-slate-700 bg-[#181a29] px-2.5 py-1 text-xs font-bold text-slate-100 shadow-inner"
                        >
                          {key}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between border-t border-slate-800/80 bg-[#0a0b12] px-6 py-3 font-mono text-xs text-slate-400">
          <div className="flex items-center gap-1.5">
            <Command className="size-3.5 text-indigo-400" aria-hidden="true" />
            <span>
              Press <kbd className="font-bold text-slate-200">?</kbd> anywhere to toggle
            </span>
          </div>
          <span>
            Press <kbd className="font-bold text-slate-200">Esc</kbd> to dismiss
          </span>
        </div>
      </div>
    </div>
  );
}
