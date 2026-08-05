import artifacts from '@/artifacts.json';

/**
 * Real evidence objects, captured by site/scripts/gen_artifacts.py:
 * a tau node receipt from the roundtable run that designed this site,
 * a live drift audit of this page against the repo, and the inventory
 * provenance. Excerpts carry SHA-256 prefixes of their sources.
 */
export function ReceiptsSection() {
  return (
    <section
      id="receipts"
      className="surface scroll-mt-14 border-b border-line py-16 md:py-20"
    >
      <h2 className="mb-2 font-display text-[clamp(2rem,3.6vw,3.4rem)]">
        Receipts, on the page
      </h2>
      <p className="mb-3 max-w-[64ch] text-mute">
        This site practices what it claims. Its design direction was decided by
        a four-seat model roundtable compiled through t&apos;au — and that run
        produced receipts like every other. Here they are, along with the live
        checks that keep this page honest.
      </p>
      <p className="machine mb-10 text-mute">
        captured by {`site/scripts/gen_artifacts.py`} @ {artifacts.commit} ·{' '}
        {artifacts.as_of}
      </p>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {artifacts.artifacts.map((a) => (
          <figure key={a.id} className="code-plate">
            <figcaption className="mb-2">
              <div className="text-[15px] font-semibold">{a.title}</div>
              <div className="machine mt-1 text-mute">{a.caption}</div>
            </figcaption>
            <pre className="machine overflow-x-auto rounded border border-line bg-fill/40 p-4 leading-relaxed text-ink">
              {a.body}
            </pre>
          </figure>
        ))}
      </div>
    </section>
  );
}
