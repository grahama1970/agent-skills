import contradiction from '@/hero-contradiction.json';

type HeroContradiction = {
  reported_claim: string;
  observed_evidence: string;
  artifact_path: string;
  artifact_digest: string;
  deterministic_rule: string;
  bounded_judgment: string;
  does_not_prove: string;
  source_url: string;
};

const data = contradiction as HeroContradiction;

export function HeroContradictionPlate() {
  return (
    <article className="hero-plate" aria-label="One real contradiction and bounded judgment">
      <div className="hero-plate__head">
        <span>False-success check</span>
        <a
          href={data.source_url}
          data-qid="hero-plate:source"
          data-qs-action="HERO_PLATE_OPEN_SOURCE"
          title="Open the source receipt on GitHub"
        >
          source
        </a>
      </div>
      <dl className="hero-plate__fields">
        <div className="hero-plate__row hero-plate__row--claim">
          <dt>Reported claim</dt>
          <dd>{data.reported_claim}</dd>
        </div>
        <div className="hero-plate__row hero-plate__row--evidence">
          <dt>Observed evidence</dt>
          <dd>{data.observed_evidence}</dd>
        </div>
        <div className="hero-plate__row">
          <dt>Immutable locator</dt>
          <dd>
            <span className="machine">{data.artifact_path}</span>
            <span className="hero-plate__digest machine">sha256 {data.artifact_digest}</span>
          </dd>
        </div>
        <div className="hero-plate__row">
          <dt>Deterministic rule</dt>
          <dd>{data.deterministic_rule}</dd>
        </div>
        <div className="hero-plate__row hero-plate__row--judgment">
          <dt>Bounded judgment</dt>
          <dd>{data.bounded_judgment}</dd>
        </div>
        <div className="hero-plate__row hero-plate__row--boundary">
          <dt>What this does not prove</dt>
          <dd>{data.does_not_prove}</dd>
        </div>
      </dl>
    </article>
  );
}
