import inventory from '@/inventory.json';

const REPO = 'https://github.com/grahama1970/agent-skills';

/**
 * Repository telemetry strip. Every figure is emitted by
 * site/scripts/gen_inventory.py at commit time — the status cell names the
 * generator and commit instead of implying live monitoring.
 */
export function TelemetryBar() {
  const { stats, commit, as_of } = inventory;
  const pct = Math.round((stats.sanity / stats.skills) * 100);
  return (
    <div
      role="region"
      aria-label="Repository telemetry, generated at build time"
      className="machine flex flex-wrap items-center gap-x-5 gap-y-2 border border-line px-5 py-3.5"
    >
      <div className="flex items-center gap-2 text-ink">
        <span
          aria-hidden="true"
          className="inline-block h-2 w-2 rounded-full bg-accent"
        />
        <span>inventory generated · not typed</span>
      </div>
      <div aria-hidden="true" className="h-4 w-px bg-line" />
      <div>
        <strong className="text-ink">{stats.skills}</strong>{' '}
        <span className="text-mute">contracts</span>
      </div>
      <div>
        <strong className="text-ink">{stats.sanity}</strong>{' '}
        <span className="border border-accent px-1.5 py-0.5 text-accent">
          sanity-checked · {pct}%
        </span>
      </div>
      <div>
        <strong className="text-ink">{stats.agents}</strong>{' '}
        <span className="text-mute">bounded agents</span>
      </div>
      <div aria-hidden="true" className="h-4 w-px bg-line" />
      <div className="text-mute">
        <a
          href={`${REPO}/commit/${commit}`}
          data-qid="telemetry:link:commit"
          data-qs-action="TELEMETRY_OPEN_COMMIT"
          title={`Open commit ${commit} on GitHub`}
          className="text-accent no-underline hover:underline"
        >
          {commit}
        </a>{' '}
        · {as_of} · {inventory.generator}
      </div>
    </div>
  );
}
