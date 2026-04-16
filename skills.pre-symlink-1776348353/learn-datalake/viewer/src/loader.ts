// Data loader — ALL data from embry-memory at localhost:8601 via Vite proxy /memory.
// No sample JSON. If /memory is down, functions throw and views show error banners.

import {
  listDocuments,
  recallDocuments,
  runAnalytics,
} from './api/client'
import type {
  SupervisorState,
  RunMetrics,
  WorkerState,
  CorpusCoverage,
  SectorCoverage,
  QuarantineEntry,
  ProviderInfo,
  CascadeDecisionPoint,
  CascadeEscalation,
  QualityTrendPoint,
  QualityPresetBreakdown,
} from './types'

// --- Corpus: derive sector counts from lessons collection ---

export async function loadCorpus(): Promise<CorpusCoverage | null> {
  const result = await listDocuments('lessons', 500)
  const knownSectors = ['arxiv', 'defense', 'nasa', 'nist', 'engineering', 'industry', 'adversarial']
  const sectorMap = new Map<string, number>()

  for (const doc of result.documents) {
    const meta = doc.metadata ?? (doc as Record<string, unknown>)
    const tags: string[] = (meta.tags as string[]) ?? []
    const scope = (meta.scope as string) ?? ''
    for (const sector of knownSectors) {
      if (tags.some((t: string) => t.toLowerCase().includes(sector)) || scope.toLowerCase().includes(sector)) {
        sectorMap.set(sector, (sectorMap.get(sector) ?? 0) + 1)
        break
      }
    }
  }

  // Enrich with total from analytics if available
  let lessonsTotal = result.total ?? 0
  try {
    const stats = await runAnalytics('collection_stats')
    const res = stats.result as Record<string, number> | undefined
    if (res?.lessons) lessonsTotal = res.lessons
  } catch { /* optional */ }

  const target = 500
  const sectors: SectorCoverage[] = knownSectors.map((name) => {
    const count = sectorMap.get(name) ?? 0
    return {
      name,
      total: count,
      extracted: count,
      pending: 0,
      failed: 0,
      coverage_pct: target > 0 ? Math.min(100, (count / target) * 100) : 100,
      target,
      deficit: Math.max(0, target - count),
    }
  })

  return {
    sectors,
    total_pdfs: lessonsTotal,
    total_extracted: lessonsTotal,
    overall_coverage_pct: 100,
  }
}

// --- Quarantine: recall quarantined extractions ---

export async function loadQuarantine(
  filters?: { reason?: string; domain?: string },
): Promise<QuarantineEntry[]> {
  const query = filters?.reason
    ? `quarantined PDF ${filters.reason}`
    : 'quarantined PDF extraction failure low-confidence'
  const result = await recallDocuments(query)
  return result.results.map((r) => {
    const m = r.metadata ?? {}
    return {
      id: r.key,
      filename: (m.filename as string) ?? r.key.slice(0, 25),
      path: (m.path as string) ?? '',
      category: (m.category as string) ?? (m.scope as string) ?? 'unknown',
      reason: ((m.reason as string) ?? 'low-confidence') as QuarantineEntry['reason'],
      timestamp: (m.timestamp as string) ?? new Date().toISOString(),
      pages: m.pages as number | undefined,
      extraction_time_ms: m.extraction_time_ms as number | undefined,
      fail_rate: m.fail_rate as number | undefined,
      cascade_tier: m.cascade_tier as number | undefined,
      scores: m.scores as Record<string, number> | undefined,
      error: m.error as string | undefined,
    }
  })
}

// --- Supervisors: recall pipeline state ---

const defaultMetrics: RunMetrics = {
  phase: 'unknown',
  extraction_success_count: 0,
  extraction_cached_profile_count: 0,
  extraction_failed_count: 0,
  extraction_attempts: 0,
  extraction_fail_rate_pct: 0,
  extraction_timeout_rate_pct: 0,
  timeout_model_decisions: 0,
  memory_retry_queue_count: 0,
  memory_retry_dead_letter_count: 0,
  extraction_throughput_per_hour: 0,
  workers: 0,
  worker_aggregate: { worker_count: 0, max_elapsed_seconds: 0, max_last_output_age_seconds: 0 },
  quality_gate_action: 'continue_extracting',
  quality_gate_reason: '',
}

export async function loadSupervisors(): Promise<SupervisorState[]> {
  const result = await recallDocuments('extraction pipeline supervisor status')
  if (result.results.length === 0) return []
  return result.results.map((r) => {
    const m = r.metadata ?? {}
    return {
      label: (m.label as string) ?? r.key,
      root: (m.root as string) ?? '',
      status: (m.status as string) ?? 'unknown',
      updated_at: (m.updated_at as string) ?? '',
      run_id: (m.run_id as string) ?? '',
      run_log: (m.run_log as string) ?? '',
      child_pid: (m.child_pid as number) ?? 0,
      restart_count: (m.restart_count as number) ?? 0,
      run_count: (m.run_count as number) ?? 0,
      review_heartbeat_fresh: (m.review_heartbeat_fresh as boolean) ?? false,
      review_heartbeat_age_seconds: (m.review_heartbeat_age_seconds as number) ?? 0,
      run_metrics: (m.run_metrics as RunMetrics) ?? defaultMetrics,
      failure_buckets: (m.failure_buckets as Record<string, number>) ?? {},
    }
  })
}

export async function loadSupervisor(label: string): Promise<SupervisorState | null> {
  const all = await loadSupervisors()
  return all.find((s) => s.label === label) ?? null
}

// --- Workers ---

export async function loadWorkers(): Promise<WorkerState[]> {
  const result = await recallDocuments('extraction worker status')
  return result.results.map((r) => {
    const m = r.metadata ?? {}
    return {
      completed: (m.completed as number) ?? 0,
      stats: {
        worker_id: m.worker_id as number | undefined,
        elapsed_seconds: (m.elapsed_seconds as number) ?? 0,
        last_output_age_seconds: (m.last_output_age_seconds as number) ?? 0,
      },
      current_item: (m.current_item as string) ?? '',
      last_updated: (m.last_updated as string) ?? '',
    }
  })
}

// --- Providers ---

export async function loadProviders(): Promise<ProviderInfo[]> {
  const result = await recallDocuments('file type extraction provider')
  if (result.results.length === 0) return []
  return result.results.map((r) => {
    const m = r.metadata ?? {}
    return {
      name: (m.name as string) ?? (m.provider as string) ?? r.key,
      class_name: (m.class_name as string) ?? '',
      extensions: (m.extensions as string[]) ?? [],
      extraction_count: (m.extraction_count as number) ?? 0,
      success_rate: (m.success_rate as number) ?? 0,
      avg_time_ms: (m.avg_time_ms as number) ?? 0,
      family: ((m.family as string) ?? 'document') as ProviderInfo['family'],
    }
  })
}

// --- Cascade ---

export async function loadCascade(): Promise<CascadeDecisionPoint[]> {
  const result = await recallDocuments('cascade shadow header-verdict pdf-profile pdf-strategy')
  if (result.results.length === 0) return []
  return result.results.map((r) => {
    const m = r.metadata ?? {}
    return {
      name: (m.name as string) ?? 'header-verdict',
      total_samples: (m.total_samples as number) ?? 0,
      shadow_file_size_bytes: (m.shadow_file_size_bytes as number) ?? 0,
      date_range: (m.date_range as { start: string; end: string }) ?? { start: '', end: '' },
      disposition_counts: (m.disposition_counts as Record<string, number>) ?? {},
      confidence_distribution: (m.confidence_distribution as number[]) ?? [0, 0, 0, 0, 0],
      promotion_status: ((m.promotion_status as string) ?? 'Early') as CascadeDecisionPoint['promotion_status'],
      agreement_rate: (m.agreement_rate as number) ?? 0,
      wilson_lower_bound: (m.wilson_lower_bound as number) ?? 0,
      samples_vs_threshold: (m.samples_vs_threshold as { current: number; threshold: number }) ?? { current: 0, threshold: 200 },
    }
  })
}

export async function loadCascadeEscalations(
  decisionPoint: string,
  limit?: number,
): Promise<CascadeEscalation[]> {
  const result = await recallDocuments(`cascade escalation ${decisionPoint}`)
  const results = limit ? result.results.slice(0, limit) : result.results
  return results.map((r) => {
    const m = r.metadata ?? {}
    return {
      filename: (m.filename as string) ?? r.key,
      doc_id: m.doc_id as string | undefined,
      confidence: (m.confidence as number) ?? r.score,
      rust_guess: (m.rust_guess as string) ?? 'unknown',
      features: (m.features as Record<string, number | boolean | string>) ?? {},
      timestamp: m.timestamp as string | undefined,
    }
  })
}

// --- Quality: return empty — views generate mock or use /analytics ---

export async function loadQualityTrends(_days?: number): Promise<QualityTrendPoint[]> {
  return []
}

export async function loadQualityPresetBreakdown(_days?: number): Promise<QualityPresetBreakdown[]> {
  return []
}
