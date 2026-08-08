import competence from '@/competence.json';

/**
 * Core-competence matrix — an exhibit, not a self-assessment.
 *
 * Rows are the disciplines the skill corpus declares in its own SKILL.md
 * frontmatter; the count is the real number of skills declaring each (from
 * gen_competence.py at the deploy commit), and the projects are the flagships
 * whose research area exercises that discipline. There are no proficiency
 * ratings — a discipline with few skills reads honestly as thin, and a
 * discipline with no flagship project shows an em dash, not a fabricated one.
 */

type Discipline = {
  id: string;
  label: string;
  skillCount: number;
  lenses: string[];
  projects: { slug: string; name: string; href: string }[];
};

// Redundant, colourblind-safe lens cue — matches the constellation encoding.
const LENS: Record<string, { mark: string; label: string }> = {
  technical: { mark: '▲', label: 'technical' },
  creative: { mark: '●', label: 'creative' },
  hybrid: { mark: '◆', label: 'hybrid' },
};

export function CompetenceMatrix() {
  const rows = competence.disciplines as Discipline[];
  return (
    <div className="cm-wrap">
      <div className="cm-scroll">
        <table className="cm-table">
          <caption className="cm-caption">
            {competence.disciplineCount} disciplines across{' '}
            <span className="machine">{competence.totalSkills}</span> skills, counted from each
            skill&rsquo;s declared frontmatter at{' '}
            <span className="machine">{competence.commit}</span> · {competence.as_of}. Counts, not
            ratings.
          </caption>
          <thead>
            <tr>
              <th scope="col">Discipline</th>
              <th scope="col" className="cm-num">Skills</th>
              <th scope="col">Lens</th>
              <th scope="col">Where it shows up</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <th scope="row" className="cm-disc">{d.label}</th>
                <td className="cm-num machine">{d.skillCount}</td>
                <td className="cm-lens">
                  {d.lenses.length === 0 ? (
                    <span className="cm-dash" aria-hidden="true">—</span>
                  ) : (
                    d.lenses.map((l) => {
                      const m = LENS[l] ?? { mark: '·', label: l };
                      return (
                        <span key={l} className={`cm-lensmark cm-lens-${l}`} title={m.label}>
                          <span aria-hidden="true">{m.mark}</span>
                          <span className="sr-only">{m.label}</span>
                        </span>
                      );
                    })
                  )}
                </td>
                <td className="cm-projects">
                  {d.projects.length === 0 ? (
                    <span className="cm-dash" title="no flagship project — capability lives in the wider corpus">—</span>
                  ) : (
                    d.projects.map((p) => (
                      <a
                        key={p.slug}
                        className="cm-chip"
                        href={p.href}
                        target="_blank"
                        rel="noreferrer"
                        data-qid={`competence:project:${d.id}:${p.slug}`}
                        data-qs-action="COMPETENCE_OPEN_PROJECT"
                        title={`${p.name} — opens the skill on GitHub`}
                      >
                        {p.name}
                      </a>
                    ))
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
