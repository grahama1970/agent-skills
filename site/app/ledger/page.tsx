import inventory from '@/inventory.json';
import { SiteNav } from '@/components/site-nav';
import { SkillMosaic } from '@/components/skill-mosaic';

export default function LedgerPage() {
  return (
    <main className="depth-page" id="top">
      <SiteNav hrefBase="/" />
      <section className="depth-head">
        <div className="wrap">
          <p className="kicker">
            <b>Ledger</b> Skill inventory
          </p>
          <h1>Every contract, including the ones without checks.</h1>
          <p className="lede">
            {inventory.stats.skills} skill contracts; {inventory.stats.sanity} with tracked check scripts.
            Counts are generated from source, not hand-entered marketing numbers; check-script presence is not latest-run proof.
          </p>
        </div>
      </section>
      <section>
        <div className="wrap">
          <SkillMosaic />
        </div>
      </section>
    </main>
  );
}
