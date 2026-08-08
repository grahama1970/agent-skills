// Environment-agnostic capability-search ranking core. No imports: the caller
// injects MiniSearch and the document list, so the SAME ranking code runs in the
// Next UI (via lib/search.ts) and in scripts/search_fixture.mjs. Keep this the
// single source of truth for retrieval behaviour (#1292).

// Field-weighted BM25: names and aliases dominate, prose supports.
export const BOOST = { name: 4, aliases: 3, area: 2, question: 1.5, summary: 1.2, body: 0.6 };

const INDEX_FIELDS = ['name', 'aliases', 'area', 'disciplines', 'question', 'summary', 'body', 'category'];
const STORE_FIELDS = ['type', 'name', 'slug', 'area', 'href', 'question', 'summary', 'visibility', 'evidenceAccess', 'scoutState'];

const FIELD_RANK = ['name', 'aliases', 'area', 'question', 'disciplines', 'summary', 'body', 'category'];
const FIELD_LABEL = {
  name: 'the name',
  aliases: 'an alias',
  area: 'the area',
  question: 'the research question',
  disciplines: 'a discipline',
  summary: 'the description',
  body: 'the write-up',
  category: 'the category',
};

/** Build the MiniSearch index. `MiniSearch` is injected so this file imports nothing. */
export function makeIndex(MiniSearch, docs) {
  const ms = new MiniSearch({
    fields: INDEX_FIELDS,
    storeFields: STORE_FIELDS,
    extractField: (doc, field) => {
      const v = doc[field];
      return Array.isArray(v) ? v.join(' ') : (v ?? '');
    },
  });
  ms.addAll(docs);
  return ms;
}

export function reasonFor(r) {
  const fields = new Set();
  Object.values(r.match ?? {}).forEach((fs) => fs.forEach((f) => fields.add(f)));
  const top = FIELD_RANK.find((f) => fields.has(f));
  if (!top) return null;
  const terms = (r.terms ?? []).slice(0, 3).join(' ');
  return { terms, where: FIELD_LABEL[top] ?? top };
}

/**
 * Two-pass retrieval: precise first — exact/alias/prefix, no fuzz — and only
 * fall back to controlled fuzzy when the precise pass is thin. Short codenames
 * never fuzz. Exact/prefix hits always rank above fuzzy ones; every hit carries
 * why it matched.
 */
export function runSearch(index, q) {
  const precise = index.search(q, { boost: BOOST, prefix: true, fuzzy: false, combineWith: 'AND' });
  let raw = precise;
  let fuzzed = false;
  if (precise.length < 3) {
    const loose = index.search(q, {
      boost: BOOST,
      prefix: true,
      fuzzy: (term) => (term.length > 4 ? 0.2 : false),
      combineWith: 'OR',
    });
    const seen = new Set(precise.map((r) => r.id));
    raw = [...precise, ...loose.filter((r) => !seen.has(r.id))];
    fuzzed = precise.length === 0;
  }
  // Exact whole-name match is the strongest possible signal: a query that IS a
  // doc's name must rank first, even against a longer prefix sibling that BM25
  // happened to score higher across other fields (e.g. "assistant" vs
  // "assistant-lab"). Stable-promote exact-name hits; everything else keeps order.
  const exact = q.trim().toLowerCase();
  raw = raw
    .map((r, i) => [r, i])
    .sort((a, b) => {
      const ae = (a[0].name ?? '').toLowerCase() === exact ? 1 : 0;
      const be = (b[0].name ?? '').toLowerCase() === exact ? 1 : 0;
      return be - ae || a[1] - b[1];
    })
    .map(([r]) => r);
  const hits = raw.slice(0, 8).map((r) => ({ ...r, score: r.score, reason: reasonFor(r) }));
  return { hits, fuzzed };
}
