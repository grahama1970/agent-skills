import type { AppSnapshot, EvidenceCard, RetrievalLane } from "@/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${detail || response.statusText}`);
  }
  return (await response.json()) as T;
}

export const api = {
  state: () => request<AppSnapshot>("/api/state"),
  start: (consentConfirmed = false) =>
    request<AppSnapshot>("/api/session/start", {
      method: "POST",
      body: JSON.stringify({ consent_confirmed: consentConfirmed }),
    }),
  pause: () => request<AppSnapshot>("/api/session/pause", { method: "POST" }),
  resume: () => request<AppSnapshot>("/api/session/resume", { method: "POST" }),
  archive: () => request<Record<string, unknown>>("/api/session/archive", { method: "POST" }),
  stop: () => request<AppSnapshot>("/api/session/stop", { method: "POST" }),
  search: (query: string, lane: RetrievalLane) =>
    request<EvidenceCard>("/api/search", {
      method: "POST",
      body: JSON.stringify({ query, lane }),
    }),
  pin: (cardId: string) => request<AppSnapshot>(`/api/cards/${cardId}/pin`, { method: "POST" }),
  dismiss: (cardId: string) =>
    request<AppSnapshot>(`/api/cards/${cardId}/dismiss`, { method: "POST" }),
};
