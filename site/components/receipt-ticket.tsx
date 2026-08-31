'use client';

import { useState } from 'react';

/** Paper-ticket receipt with distinct captured and unavailable states. The
 *  captured view can expose raw payload; unavailable records expose failure
 *  diagnostics without pretending a receipt body or digest exists. */
export function ReceiptTicket({
  id,
  title,
  callout,
  proves,
  doesNotProve,
  body,
  caption,
  captureStatus = 'captured',
  unavailableReason,
}: {
  id: string;
  title: string;
  callout: string;
  proves: string;
  doesNotProve: string;
  body: string;
  caption: string;
  captureStatus?: 'captured' | 'unavailable';
  unavailableReason?: string;
}) {
  const [raw, setRaw] = useState(false);
  const isUnavailable = captureStatus === 'unavailable';
  const panelId = `receipt-detail-${id}`;
  const detail = isUnavailable ? unavailableReason || caption : body;
  return (
    <article className="ticket" data-capture-status={captureStatus}>
      <h3>{title}</h3>
      <p className="callout">{callout}</p>
      <p className="proves">{proves}</p>
      <p className="does-not-prove">{doesNotProve}</p>
      <button
        type="button"
        data-qid={`receipts:toggle:${id}`}
        data-qs-action="RECEIPTS_TOGGLE_VIEW"
        title={raw ? 'Return to the plain summary' : isUnavailable ? 'Inspect failed capture details' : 'Inspect the raw receipt payload'}
        onClick={() => setRaw(!raw)}
        className="ticket-toggle"
        aria-expanded={raw}
        aria-controls={panelId}
      >
        {raw ? '← return to summary' : isUnavailable ? 'inspect failed capture details →' : 'inspect raw receipt →'}
      </button>
      {raw ? (
        <pre id={panelId} className="json">{detail}</pre>
      ) : isUnavailable ? (
        <p id={panelId} className="human">
          {caption}. No digest or raw receipt exists for this attempt; the failed
          capture details are inspectable separately.
        </p>
      ) : (
        <p id={panelId} className="human">
          {caption}. The judgment, proof boundary, and raw payload stay together;
          the summary is never the only evidence.
        </p>
      )}
      <p className="foot">{caption}</p>
    </article>
  );
}
