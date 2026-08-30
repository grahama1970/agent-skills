type Project = {
  name: string;
  slug: string;
  href: string;
  question: string;
  blurb: string;
  why: string;
};

type TauCaseProps = {
  project: Project;
};

const steps = [
  ['Goal', 'Contain agent work with a goal, evidence, receipt, and stop condition.'],
  ['Bounded dispatch', 'Subagents run under contracts instead of open-ended delegation.'],
  ['Captured execution', 'The public sanity receipt records exit code 0 and 45 passed.'],
  ['Boundary', 'The receipt names browser UI and live-provider semantics as unproved.'],
  ['Receipt', 'skills/tau/proofs/p0-operator-wrapper-20260705T1200Z/sanity.json'],
];

export function TauCase({ project }: TauCaseProps) {
  return (
    <article className="case-composition tau-case" data-case-composition="tau-causal-execution-dossier">
      <div className="tau-case__copy">
        <p className="kicker">
          <b>01</b> Dominant investigation
        </p>
        <h2 className="h2">{project.question}</h2>
        <p className="lede">{project.why}</p>
        <ol className="tau-case__chain" aria-label="Tau causal execution dossier">
          {steps.map(([label, value]) => (
            <li key={label}>
              <span>{label}</span>
              <b>{value}</b>
            </li>
          ))}
        </ol>
        <p className="case-note">What remains unproved: equal proof depth across every skill and fresh live-provider behavior.</p>
      </div>
      <a
        className="tau-case__artifact"
        href={project.href}
        data-qid={`case:tau:artifact:${project.slug}`}
        data-qs-action="CASE_TAU_OPEN_ARTIFACT"
        title={`Open ${project.name} source artifact`}
      >
        <img
          src="/artifacts/tau-dag-ledger-card.svg"
          alt="Animated Tau DAG card showing ask routed through Tau, a Tau-owned scillm adapter, receipt admission, and an inspectable ledger."
        />
        <span>{project.name}</span>
        <b>{project.blurb}</b>
      </a>
    </article>
  );
}
