const LINES: Array<{ t: string; agent?: string; ok?: boolean; text: string }> = [
  { t: '00:00.14', agent: 'tau', text: 'compile dag — creator → reviewer → judge' },
  { t: '00:02.51', agent: 'creator', text: 'patch drafted · 3 files · worktree isolated' },
  { t: '00:19.08', agent: 'reviewer', text: '2 findings · 1 confirmed · fix applied' },
  { t: '00:31.44', agent: 'judge', text: 'VERDICT: PASS · evidence attached' },
  { t: '00:31.62', agent: 'tau', text: 'receipt written → run-receipt.json' },
  { t: '00:31.90', ok: true, text: '✓ verified  independent read-back · hash match' },
  { t: '--:--.--', text: 'no claim ships without a receipt.' },
];

export function Trace() {
  return (
    <div
      className="mt-11 overflow-x-auto rounded-md border border-line bg-panel px-6 py-5 font-mono text-[13px] leading-[1.9]"
      role="img"
      aria-label="An agent pipeline trace: plan compiled, creator and reviewer agents run, verdict passes, receipt written and independently verified"
    >
      {LINES.map((l, i) => (
        <div
          key={l.t + l.text}
          className={`trace-line whitespace-nowrap${i === LINES.length - 1 ? ' trace-caret' : ''}`}
          style={{ animationDelay: `${0.2 + i * 0.55}s` }}
        >
          <span className="text-mute">{l.t}</span>
          {'  '}
          {l.ok ? (
            <span className="text-ok">{l.text}</span>
          ) : l.agent ? (
            <>
              <span className="text-accent">{l.agent.padEnd(9)}</span>
              <span>{l.text}</span>
            </>
          ) : (
            <span className="text-mute">{l.text}</span>
          )}
        </div>
      ))}
    </div>
  );
}
