import { useEffect, useState } from 'react';
import { WatchdogDashboard } from './components/watchdog/dashboard';
import { loadSnapshot } from './data/loadSnapshot';
import { sampleSnapshot } from './data/sampleSnapshot';
import type { WatchdogSnapshot } from './types';

export default function App() {
  const [snapshot, setSnapshot] = useState<WatchdogSnapshot>(sampleSnapshot);

  async function refresh() {
    setSnapshot(await loadSnapshot());
  }

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  return <WatchdogDashboard snapshot={snapshot} onRefresh={() => void refresh()} />;
}
