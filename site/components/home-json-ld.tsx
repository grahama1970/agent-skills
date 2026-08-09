import resumeDoc from '@/resume.json';

/**
 * schema.org graph for the homepage.
 *
 * Crawlers and recruiter or agent tooling read this before any person does, so
 * the site publishes the same Person entity the resume emits. It is read from
 * resume.json rather than restated here, so the two surfaces cannot disagree.
 */
export function HomeJsonLd() {
  const person = (resumeDoc as { jsonLd?: { '@graph'?: unknown[] } }).jsonLd?.['@graph']?.[0];
  if (!person) return null;
  const graph = {
    '@context': 'https://schema.org',
    '@graph': [
      person,
      {
        '@type': 'WebSite',
        '@id': 'https://grahama.co/#site',
        url: 'https://grahama.co',
        name: 'grahama.co',
        publisher: { '@id': 'https://grahama.co/#person' },
        inLanguage: 'en-US',
      },
    ],
  };
  return (
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }} />
  );
}
