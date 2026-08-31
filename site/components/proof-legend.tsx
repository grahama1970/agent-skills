/** How proof works (webgpt review, point 8): a first-time visitor sees badges
 *  like "check script present", "contract only", and "evidence private" on the
 *  cards below and in search. This legend decodes each one honestly — every
 *  state is a factual access level, not a quality grade. It invents no claim:
 *  it only names what the badges already on this page mean. */

const STATES: { label: string; cls: string; means: string }[] = [
  {
    label: 'check script present',
    cls: 'checked',
    means:
      'the public source contains a tracked sanity.sh for this skill. That means a checker exists; it is not proof that the latest deployment ran every check.',
  },
  {
    label: 'contract only',
    cls: 'contract',
    means:
      'the SKILL.md contract is public and readable, but I have not yet written an automated check for it. The gap is shown, not hidden.',
  },
  {
    label: 'external repo',
    cls: 'external',
    means:
      'the work lives in its own repository; the link goes to that source, not into this one.',
  },
  {
    label: 'evidence private',
    cls: 'private',
    means:
      'the system is real but its code and receipts are private (client or NDA work). The link goes to a public overview — never a claim dressed up as proof.',
  },
];

export function ProofLegend() {
  return (
    <aside className="proof-legend" aria-label="How to read the evidence on this page">
      <p className="proof-legend__intro">
        Each project below carries a badge saying <em>how far you can check
        it</em>. These are access states — where the evidence lives — not grades.
      </p>
      <ul className="proof-legend__list">
        {STATES.map((s) => (
          <li key={s.label} className={`proof-legend__item proof-legend__item--${s.cls}`}>
            <span className="proof-legend__chip">{s.label}</span>
            <span className="proof-legend__means">{s.means}</span>
          </li>
        ))}
      </ul>
      <p className="proof-legend__foot">
        A public overview never borrows the evidence status of another source,
        and a null or blocked result is publishable on the same footing as a
        passing one.
      </p>
    </aside>
  );
}
