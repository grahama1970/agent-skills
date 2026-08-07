'use client';

import { useState } from 'react';

/** Paper-ticket receipt with a Human / Raw JSON toggle. The human view is
 *  the callout + caption; raw is the captured payload, untouched. */
export function ReceiptTicket({
  id,
  title,
  callout,
  proves,
  body,
  caption,
}: {
  id: string;
  title: string;
  callout: string;
  proves: string;
  body: string;
  caption: string;
}) {
  const [raw, setRaw] = useState(false);
  return (
    <article className="ticket">
      <h3>{title}</h3>
      <p className="callout">{callout}</p>
      <p className="proves">{proves}</p>
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
          {caption}. The verdict and what it proves are above; the raw payload
          is one click away — the summary is never the only evidence.
        </p>
      )}
      <p className="foot">{caption}</p>
    </article>
  );
}
