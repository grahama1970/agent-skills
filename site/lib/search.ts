import MiniSearch from 'minisearch';
import catalog from '@/catalog.json';
import { makeIndex, runSearch as coreRunSearch } from '@/lib/search-core.mjs';

/** Typed UI wrapper over the shared ranking core (lib/search-core.mjs). The core
 *  is the single source of truth so the fixture test exercises the shipped code. */

export interface Doc {
  id: string;
  type: 'area' | 'project' | 'skill';
  name: string;
  slug?: string;
  area?: string;
  lens?: string;
  aliases?: string[];
  disciplines?: string[];
  question?: string;
  summary?: string;
  href?: string;
  visibility?: string;
  evidenceAccess?: string;
  scoutState?: string;
  category?: string;
}

export const DOCS = catalog.documents as Doc[];

export type Hit = Doc & { score: number; reason?: { terms: string; where: string } | null };

export function buildIndex(): MiniSearch<Doc> {
  return makeIndex(MiniSearch, DOCS) as MiniSearch<Doc>;
}

export function runSearch(index: MiniSearch<Doc>, q: string): { hits: Hit[]; fuzzed: boolean } {
  return coreRunSearch(index, q) as { hits: Hit[]; fuzzed: boolean };
}
