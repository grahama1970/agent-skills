type Project = {
  name: string;
  slug: string;
  href: string;
  question: string;
};

type SpartaCaseProps = {
  project: Project;
};

export function SpartaCase({ project }: SpartaCaseProps) {
  return (
    <article className="case-composition sparta-case" data-case-composition="sparta-evidence-relationship-plate">
      <a
        className="sparta-case__artifact"
        href={project.href}
        data-qid={`case:sparta:source:${project.slug}`}
        data-qs-action="CASE_SPARTA_OPEN_SOURCE"
        title={`Open ${project.name} source`}
      >
        <img
          src="/artifacts/sparta-countermeasure-mapper-source.svg"
          alt="SPARTA countermeasure mapper excerpt connecting countermeasures, techniques, and coverage gaps."
        />
      </a>
      <div className="sparta-case__thread" aria-label="SPARTA evidence relationship thread">
        <span>Requirement / threat</span>
        <b>{project.question}</b>
        <span>Source relationship</span>
        <b>Countermeasures -&gt; techniques/sub-techniques -&gt; coverage gaps.</b>
        <span>Judgment boundary</span>
        <b>Public source excerpt only; not a full corpus audit.</b>
      </div>
    </article>
  );
}
