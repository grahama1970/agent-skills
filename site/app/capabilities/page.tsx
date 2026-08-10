import { CompetenceMatrix } from '@/components/competence-matrix';
import { SiteNav } from '@/components/site-nav';

export default function CapabilitiesPage() {
  return (
    <main className="depth-page" id="top">
      <SiteNav hrefBase="/" />
      <section className="depth-head">
        <div className="wrap">
          <p className="kicker">
            <b>Capabilities</b> Counted from skills
          </p>
          <h1>What the work adds up to.</h1>
          <p className="lede">
            A discipline map counted from declared skill metadata. Counts, not ratings.
          </p>
        </div>
      </section>
      <section>
        <div className="wrap">
          <CompetenceMatrix />
        </div>
      </section>
    </main>
  );
}
