import { sampleSnapshot } from './sampleSnapshot';
import type { WatchdogSnapshot } from '../types';

const SNAPSHOT_URL = '/project-watchdog-snapshot.json';

export async function loadSnapshot(): Promise<WatchdogSnapshot> {
  try {
    const response = await fetch(`${SNAPSHOT_URL}?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) return sampleSnapshot;
    const payload = (await response.json()) as WatchdogSnapshot;
    if (payload.schema !== 'agent_skills.project_watchdog.ui_snapshot.v1') return sampleSnapshot;
    return payload;
  } catch {
    return sampleSnapshot;
  }
}
