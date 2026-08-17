import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { AppSnapshot, RetrievalLane } from "@/types";

const EMPTY_STATE: AppSnapshot = {
  schema: "live_evidence.app_snapshot.v1",
  session: {
    session_id: "initializing",
    status: "idle",
    consent_confirmed: false,
    profile_name: "default",
  },
  current_thread: "Waiting for the conversation",
  transcript: [],
  cards: [],
  lanes: ["memory", "code", "ripgrep", "brave", "dogpile"].map((lane) => ({
    lane: lane as RetrievalLane,
    state: lane === "brave" || lane === "dogpile" ? "disabled" : "idle",
    detail: lane === "brave" || lane === "dogpile" ? "Manual only" : "Waiting",
    result_count: 0,
    updated_at: new Date(0).toISOString(),
  })),
  external_search_enabled: false,
  updated_at: new Date(0).toISOString(),
};

export function useLiveEvidence() {
  const [snapshot, setSnapshot] = useState<AppSnapshot>(EMPTY_STATE);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .state()
      .then((state) => {
        if (active) setSnapshot(state);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load state");
      });

    const stream = new EventSource("/api/events");
    stream.addEventListener("snapshot", (event) => {
      try {
        setSnapshot(JSON.parse((event as MessageEvent<string>).data) as AppSnapshot);
        setConnected(true);
        setError(null);
      } catch {
        setError("The live state stream returned invalid data");
      }
    });
    stream.onerror = () => {
      setConnected(false);
      setError("Reconnecting to the local evidence service…");
    };

    return () => {
      active = false;
      stream.close();
    };
  }, []);

  const execute = useCallback(async <T,>(operation: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    setError(null);
    try {
      return await operation();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The operation failed");
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const actions = useMemo(
    () => ({
      start: () => execute(() => api.start(false)),
      pause: () => execute(api.pause),
      stop: () => execute(api.stop),
      search: (query: string, lane: RetrievalLane) => execute(() => api.search(query, lane)),
      pin: (cardId: string) => execute(() => api.pin(cardId)),
      dismiss: (cardId: string) => execute(() => api.dismiss(cardId)),
    }),
    [execute],
  );

  return { snapshot, connected, error, busy, actions };
}
