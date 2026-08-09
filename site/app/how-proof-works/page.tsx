import artifacts from '@/artifacts.json';
import { SiteNav } from '@/components/site-nav';
import { ProofExplainer } from '@/components/proof-explainer';
import { ReceiptTicket } from '@/components/receipt-ticket';

type ReceiptArtifact = {
  id: 'roundtable-receipt' | 'live-audit' | 'inventory-provenance';
  title: string;
  capture_status: 'captured' | 'unavailable';
  judgment: string;
  proves: string;
  does_not_prove: string;
  body: string;
  caption: string;
};

export default function HowProofWorksPage() {
  const receipts = artifacts.artifacts as ReceiptArtifact[];

  return (
    <main className="depth-page" id="top">
      <SiteNav hrefBase="/" />
      <section className="depth-head">
        <div className="wrap">
          <p className="kicker">
            <b>Proof</b> Method route
          </p>
          <h1>One real run, from goal to receipt.</h1>
          <p className="lede">
            Each step resolves to a real artifact and states what it does not prove.
          </p>
        </div>
      </section>
      <section>
        <div className="wrap">
          <ProofExplainer />
        </div>
      </section>
      <section>
        <div className="wrap receipt-depth-grid">
          {receipts
            .filter((receipt) => receipt.capture_status === 'captured')
            .map((receipt) => (
              <ReceiptTicket
                key={receipt.id}
                id={receipt.id}
                title={receipt.title}
                callout={receipt.judgment}
                proves={receipt.proves}
                doesNotProve={receipt.does_not_prove}
                body={receipt.body}
                caption={receipt.caption}
              />
            ))}
        </div>
      </section>
    </main>
  );
}
