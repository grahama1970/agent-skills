type Project = {
  name: string;
  slug: string;
  href: string;
  question: string;
};

type PersonaDreamCaseProps = {
  project: Project;
};

export function PersonaDreamCase({ project }: PersonaDreamCaseProps) {
  return (
    <article className="case-composition persona-case" data-case-composition="persona-dream-experiment-sequence">
      <div className="persona-case__sequence" aria-label="persona-dream experiment sequence">
        <span>Memory residue</span>
        <b>Recorded seed idea only.</b>
        <span>Generated dream</span>
        <b>Synthetic project output is labeled as output, never proof.</b>
        <span>Measured state</span>
        <b>PASS_RECORDED_IDEA_ONLY.</b>
        <span>Boundary</span>
        <b>No persona memories, story completeness, or panel quality established.</b>
      </div>
      <a
        className="persona-case__artifact"
        href={project.href}
        data-qid={`case:persona-dream:source:${project.slug}`}
        data-qs-action="CASE_PERSONA_DREAM_OPEN_SOURCE"
        title={`Open ${project.name} source`}
      >
        <img
          src="/artifacts/persona-dream-idea-gate-receipt.svg"
          alt="persona-dream idea gate receipt showing PASS_RECORDED_IDEA_ONLY and does-not-prove boundaries."
        />
        <b>{project.question}</b>
      </a>
    </article>
  );
}
