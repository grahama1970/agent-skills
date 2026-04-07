// Mock stub data for V8 ThreatMatrixView, V9 LemmaGraphView, V10 MonitorView

import type {
  ThreatCell,
  ThreatDrillthrough,
  EvidenceCase,
  LemmaNode,
  LemmaEdge,
  MonitorService,
  MonitorEvent,
} from '../types';

// --- V8 ThreatMatrixView ---

export const MOCK_THREAT_CELLS: ThreatCell[] = [
  {
    controlId: 'AC-2',
    controlName: 'Account Management',
    sector: 'defense',
    coverageScore: 0.87,
    evidenceCount: 12,
    status: 'covered',
  },
  {
    controlId: 'AC-3',
    controlName: 'Access Enforcement',
    sector: 'defense',
    coverageScore: 0.55,
    evidenceCount: 6,
    status: 'partial',
  },
  {
    controlId: 'IA-5',
    controlName: 'Authenticator Management',
    sector: 'nist',
    coverageScore: 0.91,
    evidenceCount: 18,
    status: 'covered',
  },
  {
    controlId: 'SI-3',
    controlName: 'Malicious Code Protection',
    sector: 'nist',
    coverageScore: 0.12,
    evidenceCount: 2,
    status: 'gap',
  },
  {
    controlId: 'CM-6',
    controlName: 'Configuration Settings',
    sector: 'engineering',
    coverageScore: 0.44,
    evidenceCount: 5,
    status: 'partial',
  },
];

export const MOCK_EVIDENCE_CASES: EvidenceCase[] = [
  {
    id: 'ec-001',
    claim: 'System enforces account lockout after 5 failed login attempts',
    verdict: 'supported',
    confidence: 0.93,
    sources: ['NIST SP 800-53 Rev 5 AC-7', 'System Security Plan v2.1'],
    createdAt: '2026-03-10T14:22:00Z',
  },
  {
    id: 'ec-002',
    claim: 'Privileged accounts are reviewed quarterly',
    verdict: 'insufficient',
    confidence: 0.61,
    sources: ['Audit Log 2026-Q1'],
    createdAt: '2026-03-11T09:05:00Z',
  },
  {
    id: 'ec-003',
    claim: 'Service accounts are disabled when not in use',
    verdict: 'supported',
    confidence: 0.88,
    sources: ['ITSM Ticket #4491', 'AD Audit Report Mar 2026'],
    createdAt: '2026-03-12T11:30:00Z',
  },
];

export const MOCK_THREAT_DRILLTHROUGH: ThreatDrillthrough = {
  cell: MOCK_THREAT_CELLS[0],
  evidenceCases: MOCK_EVIDENCE_CASES,
  relatedControls: ['AC-3', 'AC-6', 'IA-4'],
  spartaMapping: 'SS-005',
};

// --- V9 LemmaGraphView ---

export const MOCK_LEMMA_NODES: LemmaNode[] = [
  {
    id: 'L001',
    label: 'AccessControlInvariant',
    proofStatus: 'proven',
    dependencyCount: 3,
    impactScore: 0.95,
    lean4Snippet: 'theorem access_control_invariant : ∀ u : User, authenticated u → authorized u →',
    requirementIds: ['AC-2', 'AC-3'],
  },
  {
    id: 'L002',
    label: 'AuthTokenExpiry',
    proofStatus: 'proven',
    dependencyCount: 1,
    impactScore: 0.72,
    lean4Snippet: 'theorem auth_token_expiry : ∀ t : Token, expired t → ¬ valid t',
    requirementIds: ['IA-5'],
  },
  {
    id: 'L003',
    label: 'SessionIsolation',
    proofStatus: 'partial',
    dependencyCount: 2,
    impactScore: 0.81,
    lean4Snippet: 'theorem session_isolation : ∀ s1 s2 : Session, s1 ≠ s2 →',
    requirementIds: ['AC-3', 'SC-23'],
  },
  {
    id: 'L004',
    label: 'AuditLogIntegrity',
    proofStatus: 'unproven',
    dependencyCount: 4,
    impactScore: 0.68,
    requirementIds: ['AU-9'],
  },
  {
    id: 'L005',
    label: 'LeastPrivilegeAxiom',
    proofStatus: 'axiom',
    dependencyCount: 0,
    impactScore: 1.0,
    lean4Snippet: 'axiom least_privilege : ∀ p : Principal, permissions p ⊆ min_required p',
    requirementIds: ['AC-6'],
  },
  {
    id: 'L006',
    label: 'CryptoKeyRotation',
    proofStatus: 'proven',
    dependencyCount: 1,
    impactScore: 0.77,
    lean4Snippet: 'theorem crypto_key_rotation : ∀ k : Key, age k > rotation_period → revoked k',
    requirementIds: ['IA-5', 'SC-12'],
  },
  {
    id: 'L007',
    label: 'MalwareIsolation',
    proofStatus: 'unproven',
    dependencyCount: 3,
    impactScore: 0.59,
    requirementIds: ['SI-3'],
  },
  {
    id: 'L008',
    label: 'ConfigurationBaseline',
    proofStatus: 'partial',
    dependencyCount: 2,
    impactScore: 0.63,
    lean4Snippet: 'theorem config_baseline : ∀ c : Config, approved c → compliant c',
    requirementIds: ['CM-6'],
  },
];

export const MOCK_LEMMA_EDGES: LemmaEdge[] = [
  { source: 'L001', target: 'L005', relation: 'depends_on', strength: 0.95 },
  { source: 'L001', target: 'L002', relation: 'depends_on', strength: 0.78 },
  { source: 'L002', target: 'L006', relation: 'proves', strength: 0.82 },
  { source: 'L003', target: 'L001', relation: 'depends_on', strength: 0.71 },
  { source: 'L003', target: 'L002', relation: 'depends_on', strength: 0.65 },
  { source: 'L004', target: 'L001', relation: 'depends_on', strength: 0.58 },
  { source: 'L006', target: 'L005', relation: 'depends_on', strength: 0.90 },
  { source: 'L007', target: 'L004', relation: 'depends_on', strength: 0.44 },
  { source: 'L008', target: 'L005', relation: 'depends_on', strength: 0.67 },
  { source: 'L007', target: 'L003', relation: 'contradicts', strength: 0.31 },
];

// --- V10 MonitorView ---

export const MOCK_MONITOR_SERVICES: MonitorService[] = [
  {
    name: 'extract-pdf',
    status: 'healthy',
    lastCheck: '2026-03-16T07:20:00Z',
    latencyMs: 68,
    errorRate: 0.0,
    details: '4491 tests pass, cascade 3/3 healthy',
  },
  {
    name: 'learn-datalake',
    status: 'healthy',
    lastCheck: '2026-03-16T07:18:00Z',
    latencyMs: 120,
    errorRate: 0.01,
    details: '2819 PDFs seeded, 540K shadow entries',
  },
  {
    name: 'arangodb',
    status: 'healthy',
    lastCheck: '2026-03-16T07:15:00Z',
    latencyMs: 4,
    errorRate: 0.0,
    details: 'Cluster healthy, replication lag 0ms',
  },
  {
    name: 'cascade-runner',
    status: 'degraded',
    lastCheck: '2026-03-16T07:10:00Z',
    latencyMs: 340,
    errorRate: 0.08,
    details: 'Tier 0.5 classifier latency elevated (340ms vs 50ms baseline)',
  },
  {
    name: 'monitor-drift-sensors',
    status: 'healthy',
    lastCheck: '2026-03-16T07:05:00Z',
    latencyMs: 15,
    errorRate: 0.0,
    details: 'CUSUM/Page-Hinkley nominal on all 3 decision points',
  },
  {
    name: 'pdf-harvest-worker',
    status: 'down',
    lastCheck: '2026-03-16T06:45:00Z',
    details: 'Worker exited: OOM on 1.2GB arxiv archive. Auto-restart queued.',
  },
];

export const MOCK_MONITOR_EVENTS: MonitorEvent[] = [
  {
    timestamp: '2026-03-16T07:20:00Z',
    source: 'extract-pdf',
    level: 'info',
    message: 'Sanity PASS: 4491 tests, 0 regressions, cascade 3/3 healthy',
    linkTo: 'extract-pdf',
  },
  {
    timestamp: '2026-03-16T07:18:00Z',
    source: 'monitor-codebase',
    level: 'info',
    message: 'pdf_oxide: 0 lint issues, 0 type errors, 4491 tests pass',
    linkTo: 'corpus',
  },
  {
    timestamp: '2026-03-16T07:10:00Z',
    source: 'cascade-runner',
    level: 'warn',
    message: 'Tier 0.5 classifier latency 340ms — threshold 200ms. Investigating model load.',
    linkTo: 'cascade',
  },
  {
    timestamp: '2026-03-16T07:05:00Z',
    source: 'monitor-drift-sensors',
    level: 'info',
    message: 'CUSUM alert cleared: header-verdict agreement back above 90% on nist preset',
    linkTo: 'cascade',
  },
  {
    timestamp: '2026-03-16T06:55:00Z',
    source: 'learn-datalake',
    level: 'info',
    message: 'Nightly run complete: 540,618 shadow entries, 97.9% escalation resolution',
  },
  {
    timestamp: '2026-03-16T06:45:00Z',
    source: 'pdf-harvest-worker',
    level: 'error',
    message: 'Worker OOM on arxiv/1234567.pdf (1.2GB). Requeued with memory limit 4GB.',
    linkTo: 'quarantine',
  },
  {
    timestamp: '2026-03-16T05:30:00Z',
    source: 'monitor-drift-sensors',
    level: 'warn',
    message: 'CUSUM alert: header-verdict agreement dropped 91.2% → 88.7% on nist preset (last 48h)',
    linkTo: 'cascade',
  },
  {
    timestamp: '2026-03-16T04:00:00Z',
    source: 'arangodb',
    level: 'info',
    message: 'Nightly backup complete: 12.4GB, 0 errors, retention 30d',
  },
  {
    timestamp: '2026-03-15T23:00:00Z',
    source: 'monitor-skill-health',
    level: 'info',
    message: 'All 8 monitored skills healthy. header-verdict F1=0.9979 stable.',
  },
  {
    timestamp: '2026-03-15T20:15:00Z',
    source: 'cascade-runner',
    level: 'error',
    message: 'pdf-strategy shadow write failed: disk quota on ~/.pi/skills/extract-pdf/shadow/ (98% full)',
    linkTo: 'cascade',
  },
];
