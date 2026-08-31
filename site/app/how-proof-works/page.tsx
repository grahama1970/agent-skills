import artifacts from '@/artifacts.json';
import { SiteNav } from '@/components/site-nav';
import { ProofExplainer } from '@/components/proof-explainer';
import { ReceiptTicket } from '@/components/receipt-ticket';

type ReceiptArtifact = {
  id: string;
  title: string;
  capture_status: 'captured' | 'unavailable';
  judgment: string;
  proves: string;
  does_not_prove: string;
  body: string;
  caption: string;
  unavailable_reason?: string;
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
          <div className="inspection-protocol">
            <p className="kicker">
              <b>Inspect</b> Repository path
            </p>
            <h2 className="h2">Ask an agent to trace the work through source.</h2>
            <ol className="hero-trace-protocol" aria-label="Repository inspection path">
              <li>
                <span>Start</span>
                <code>skills/*/SKILL.md</code>
              </li>
              <li>
                <span>Check</span>
                <code>skills/monitor-website/run.sh</code>
              </li>
              <li>
                <span>Inspect</span>
                <code>site/design-roundtable/*</code>
              </li>
              <li>
                <span>Stop</span>
                <code>NOT_TESTED stays visible</code>
              </li>
            </ol>
          </div>
          <ProofExplainer />
        </div>
      </section>
      <section>
        <div className="wrap receipt-depth-grid">
          {receipts.map((receipt) => (
            <ReceiptTicket
              key={receipt.id}
              id={receipt.id}
              title={receipt.title}
              callout={receipt.judgment}
              proves={receipt.proves}
              doesNotProve={receipt.does_not_prove}
              body={receipt.body || receipt.unavailable_reason || receipt.caption}
              caption={receipt.caption}
            />
          ))}
        </div>
      </section>
    </main>
  );
}
