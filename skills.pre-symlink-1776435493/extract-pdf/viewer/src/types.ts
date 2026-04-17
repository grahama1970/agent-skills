// Profile from pdf_oxide survey
export interface DocumentProfile {
  domain: string;
  preset: string;
  complexity_score: number;
  page_count: number;
  is_scanned: boolean;
  primary_font?: string;
  primary_font_size?: number;
  strategy?: string;
}

// Text block from classify_blocks
export interface Block {
  id: string;
  page: number;
  bbox: [number, number, number, number];
  text: string;
  block_type: string; // "Header" | "Body" | "Boilerplate" | "Caption" | "Footnote"
  font_size: number;
  is_header: boolean;
  header_level?: number;
  header_disposition?: string; // "Accept" | "Reject" | "Escalate"
  taxonomy_tags?: string[]; // e.g. ["heart:trust", "mind:technical"]
}

// Section from build_flat_sections
export interface Section {
  title: string;
  display_title: string;
  level: number;
  section_number?: string;
  page_start: number;
  page_end: number;
  parent_idx?: number;
  header_disposition?: string;
}

// Table
export interface Table {
  page_number: number;
  bbox: [number, number, number, number];
  strategy: string;
  rows: string[][];
  score?: number;
}

// Figure
export interface Figure {
  figure_id: string;
  page: number;
  bbox: [number, number, number, number];
  image_path?: string;
  context_above?: string;
}

// Cascade decision point
export interface CascadeDecision {
  decision_point: string; // "header-verdict" | "pdf-profile" | "pdf-strategy"
  predicted: string;
  confidence: number;
  tier: number;
  features?: Record<string, number | boolean | string>;
}

// Taxonomy tag
export interface TaxonomyTag {
  text: string;
  category: "mind" | "heart"; // mind=sparta/operational, heart=behavioral/persona
  confidence: number;
}

// Top-level extraction result
export interface ExtractionResult {
  version: string;
  engine: string;
  engine_version: string;
  profile: DocumentProfile;
  blocks: Block[];
  sections: Section[];
  tables: Table[];
  figures: Figure[];
  cascade_decisions?: CascadeDecision[];
  taxonomy_tags?: TaxonomyTag[];
}

// Batch result for multiple PDFs
export interface BatchResult {
  filename: string;
  status: "success" | "error" | "timeout";
  result?: ExtractionResult;
  error?: string;
  duration_ms: number;
}
