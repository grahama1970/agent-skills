'use client';

import { useState } from 'react';

/** Paper-ticket receipt with a Human / Raw JSON toggle. The human view is
 *  the callout + caption; raw is the captured payload, untouched. */
export function ReceiptTicket({
  id,
  title,
  callout,
  body,
  caption,
}: {
  id: string;
  title: string;
  callout: string;
  body: string;
  caption: string;
}) {
  const [raw, setRaw] = useState(true);
  return (
    <article className="ticket">
      <h3>{title}</h3>
      <p className="callout">{callout}</p>
      <button
        type="button"
        data-qid={`receipts:toggle:${id}`}
        data-qs-action="RECEIPTS_TOGGLE_VIEW"
        title="Toggle between human summary and raw JSON payload"
        onClick={() => setRaw(!raw)}
        className="ticket-toggle"
      >
        [ {raw ? 'raw json' : 'human view'} ] switch
      </button>
      {raw ? (
        <pre className="json">{body}</pre>
      ) : (
        <p className="human">
          {caption}. Verdict above; full payload one click away — the summary
          is never the only evidence.
        </p>
      )}
      <p className="foot">{caption}</p>
    </article>
  );
}
