const CANDIDATE_HOSTS = [
  process.env.BATTLE_HOST,
  "http://127.0.0.1:3002",
  "http://127.0.0.1:3012",
].filter(Boolean);

export async function resolveBattleProveHost() {
  for (const host of CANDIDATE_HOSTS) {
    try {
      const response = await fetch(`${host}/`, { signal: AbortSignal.timeout(2500) });
      if (response.ok) return host;
    } catch {
      // try next host
    }
  }
  return CANDIDATE_HOSTS[0] ?? "http://127.0.0.1:3002";
}
