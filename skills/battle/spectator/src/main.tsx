import { Component, StrictMode, type ErrorInfo, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

import { BattleSpectatorRoot } from "./BattleActionRegistrar";
import { BattleSpectatorArena } from "./BattleSpectatorArena";
import "./standalone.generated.css";

if (!window.location.hash) {
  window.location.hash = "#battle";
}

const root = document.getElementById("root");
if (!root) {
  throw new Error("Battle spectator root element was not found");
}

class BattleStandaloneErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    const errors = ((window as unknown as { __battleBootErrors?: unknown[] }).__battleBootErrors ??= []);
    errors.push({
      type: "react",
      message: error.message,
      stack: error.stack,
      componentStack: info.componentStack,
    });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="grid min-h-screen place-items-center bg-background p-6 text-slate-100">
        <section className="max-w-3xl rounded-xl border border-battle-red/35 bg-battle-panel/90 p-5 shadow-redGlow">
          <h1 className="text-lg font-black text-battle-red">Battle spectator render blocked</h1>
          <pre className="mt-3 overflow-auto whitespace-pre-wrap text-sm text-slate-200">
            {this.state.error.stack ?? this.state.error.message}
          </pre>
        </section>
      </main>
    );
  }
}

createRoot(root).render(
  <StrictMode>
    <BattleStandaloneErrorBoundary>
      <BattleSpectatorRoot>
        <BattleSpectatorArena />
      </BattleSpectatorRoot>
    </BattleStandaloneErrorBoundary>
  </StrictMode>,
);
