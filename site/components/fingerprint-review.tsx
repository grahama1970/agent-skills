import Link from 'next/link';
import { getFingerprintRecord } from '@/lib/fingerprint';

type Props = {
  requestedId?: string;
};

export function FingerprintReview({ requestedId }: Props) {
  const record = getFingerprintRecord();
  const acceptedIds = new Set([
    record.candidateFingerprint,
    record.candidateFingerprint.slice(0, 16),
    record.sourceCommit,
    record.sourceCommitShort,
    undefined,
  ]);
  const idMatches = acceptedIds.has(requestedId);

  return (
    <main className="fingerprint-page">
      <section className="fingerprint-hero">
        <p className="eyebrow">
          <span className="dot" /> Public review fingerprint
        </p>
        <h1>Fingerprint-bound grahama.co review surface.</h1>
        <p>
          This route exists so WebGPT and other browser reviewers can inspect the
          deployed candidate directly, echo a public fingerprint, and avoid
          local-only loopback URLs.
        </p>
      </section>

      <section className="fingerprint-panel" aria-labelledby="fingerprint-current">
        <h2 id="fingerprint-current">Current Candidate</h2>
        <dl className="fingerprint-facts">
          <div>
            <dt>canary</dt>
            <dd>
              <code>{record.canary}</code>
            </dd>
          </div>
          <div>
            <dt>candidate_fingerprint</dt>
            <dd>
              <code>{record.candidateFingerprint}</code>
            </dd>
          </div>
          <div>
            <dt>source_commit</dt>
            <dd>
              <code>{record.sourceCommit}</code>
            </dd>
          </div>
          <div>
            <dt>manifest_source_commit</dt>
            <dd>
              <code>{record.manifestSourceCommit ?? 'not available at build time'}</code>
            </dd>
          </div>
          {requestedId ? (
            <div>
              <dt>requested_id_match</dt>
              <dd>
                <code>{idMatches ? 'MATCH' : 'MISMATCH'}</code>
              </dd>
            </div>
          ) : null}
        </dl>
      </section>

      <section className="fingerprint-panel" aria-labelledby="fingerprint-units">
        <h2 id="fingerprint-units">Review Units</h2>
        <p>
          Review these public routes as separate units. Do not judge the site
          from one full-page screenshot.
        </p>
        <ol className="fingerprint-units">
          {record.reviewUnits.map((unit) => (
            <li key={unit.id}>
              <div>
                <code>{unit.id}</code>
                <h3>{unit.label}</h3>
                <p>{unit.question}</p>
              </div>
              <Link href={unit.url}>Open unit →</Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="fingerprint-panel" aria-labelledby="fingerprint-prompt">
        <h2 id="fingerprint-prompt">Reviewer Instructions</h2>
        <p>
          A valid review must quote the canary, the candidate fingerprint, and at
          least three exact review unit IDs from this page. If those values are
          absent, the review is stale or did not inspect this route.
        </p>
        <pre className="fingerprint-prompt">{`REVIEW_CANARY: ${record.canary}
candidate_fingerprint: ${record.candidateFingerprint}
source_commit: ${record.sourceCommit}
review_unit_ids_seen: ${record.reviewUnits.map((unit) => unit.id).join(', ')}`}</pre>
      </section>
    </main>
  );
}
