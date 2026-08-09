'use client';

import { useState } from 'react';

/** Paper-ticket receipt with a Human / Raw JSON toggle. The human view is
 *  the callout + caption; raw is the captured payload, untouched. */
export function ReceiptTicket({
  id,
  title,
  callout,
  proves,
  doesNotProve,
  body,
  caption,
}: {
  id: string;
  title: string;
  callout: string;
  proves: string;
  doesNotProve: string;
  body: string;
  caption: string;
}) {
  const [raw, setRaw] = useState(false);
  return (
    <article className="ticket">
      <h3>{title}</h3>
      <p className="callout">{callout}</p>
      <p className="proves">{proves}</p>
      <p className="does-not-prove">{doesNotProve}</p>
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
        <pre className="json">{body}</pre>
      ) : (
        <p className="human">
          {caption}. The judgment, proof boundary, and raw payload stay together;
          the summary is never the only evidence.
        </p>
      )}
      <p className="foot">{caption}</p>
    </article>
  );
}
