'use client';

import { useState } from 'react';

/** Proof Workshop pilot: the receipt is not just a paper skin. It exposes the
 *  four roles the site world now depends on: claim, evidence, boundary, and
 *  bounded judgment. Raw payload remains untouched. */
export function ReceiptTicket({
  id,
  title,
  callout,
  proves,
  doesNotProve,
  body,
  caption,
  variant = 'secondary',
}: {
  id: string;
  title: string;
  callout: string;
  proves: string;
  doesNotProve: string;
  body: string;
  caption: string;
  variant?: 'primary' | 'secondary';
}) {
  const [raw, setRaw] = useState(false);
  if (variant === 'primary') {
    return (
      <article
        className="ticket ticket-primary proof-workshop-pilot"
        data-proof-pilot="receipt"
      >
        <header className="ticket-claim" data-proof-role="claim">
          <span className="proof-role-label">Claim</span>
          <h3>{title}</h3>
        </header>
        <div className="ticket-primary-grid">
          <div className="ticket-summary" data-proof-role="evidence">
            <span className="proof-role-label">Evidence</span>
            <p className="proves">{proves}</p>
            <p className="human proof-context">
              {caption}. The judgment, proof boundary, and raw payload stay together;
              the summary is never the only evidence.
            </p>
          </div>
          <div className="ticket-raw" data-proof-role="raw-artifact">
            <span className="proof-role-label">Raw artifact</span>
            <pre className="json">{body}</pre>
          </div>
        </div>
        <div className="ticket-boundary" data-proof-role="boundary">
          <span className="proof-role-label">Does not prove</span>
          <p className="does-not-prove">{doesNotProve}</p>
        </div>
        <div className="ticket-judgment" data-proof-role="judgment">
          <span className="proof-role-label">Bounded judgment</span>
          <p className="callout">{callout}</p>
        </div>
      </article>
    );
  }
  return (
    <article
      className="ticket ticket-secondary proof-workshop-pilot"
      data-proof-pilot="receipt"
    >
      <header className="ticket-claim" data-proof-role="claim">
        <span className="proof-role-label">Claim</span>
        <h3>{title}</h3>
      </header>
      <div className="ticket-summary" data-proof-role="evidence">
        <span className="proof-role-label">Evidence</span>
        <p className="proves">{proves}</p>
      </div>
      <button
        type="button"
        data-qid={`receipts:toggle:${id}`}
        data-qs-action="RECEIPTS_TOGGLE_VIEW"
        title={raw ? 'Return to the plain summary' : 'Inspect the raw receipt payload'}
        onClick={() => setRaw(!raw)}
        className="ticket-toggle"
      >
        {raw ? '← return to summary' : 'inspect raw receipt →'}
      </button>
      {raw ? (
        <div className="ticket-raw" data-proof-role="raw-artifact">
          <span className="proof-role-label">Raw artifact</span>
          <pre className="json">{body}</pre>
        </div>
      ) : (
        <p className="human proof-context">
          {caption}. The judgment, proof boundary, and raw payload stay together;
          the summary is never the only evidence.
        </p>
      )}
      <div className="ticket-boundary" data-proof-role="boundary">
        <span className="proof-role-label">Does not prove</span>
        <p className="does-not-prove">{doesNotProve}</p>
      </div>
      <div className="ticket-judgment" data-proof-role="judgment">
        <span className="proof-role-label">Bounded judgment</span>
        <p className="callout">{callout}</p>
      </div>
    </article>
  );
}
