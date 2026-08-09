import { CapabilitySearch } from '@/components/capability-search';
import { CapabilityConstellation } from '@/components/capability-constellation';
import { SiteNav } from '@/components/site-nav';

export default function ExplorePage() {
  return (
    <main className="depth-page" id="top">
      <SiteNav hrefBase="/" />
      <section className="depth-head">
        <div className="wrap">
          <p className="kicker">
            <b>Explore</b> Project fit
          </p>
          <h1>Search the practice by problem.</h1>
        </div>
      </section>
      <section className="search-band">
        <div className="wrap">
          <CapabilitySearch />
          <CapabilityConstellation />
        </div>
      </section>
    </main>
  );
}
