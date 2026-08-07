/**
 * ScriptCoverageTable, extracted from DreamWorkspace.tsx.
 */
import { nvis } from '../styles'
import { Table2 } from 'lucide-react'


export function ScriptCoverageTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return null
  return (
    <div data-qid="dream:script:interaction-matrix-coverage" style={nvis.scriptCoverage}>
      <div style={nvis.scriptCoverageTitle}><Table2 size={12} /> Interaction Matrix Coverage</div>
      <div style={nvis.scriptCoverageGrid}>
        {rows.map((row, index) => {
          const entity = String(row.entity ?? row.name ?? row.source_seed_id ?? `row-${index + 1}`)
          const described = row.described_in_script === true || row.covered === true || row.covered_in_script === true
          const objects = Array.isArray(row.objects_used) ? row.objects_used : Array.isArray(row.objects) ? row.objects : []
          return (
            <div key={`${String(row.source_seed_id ?? entity)}-${index}`} style={nvis.scriptCoverageRow}>
              <div style={nvis.scriptCoverageMeta}>
                <span style={nvis.scriptElementTag}>{String(row.source_seed_id ?? `seed-${index}`)}</span>
                <span style={described ? nvis.scriptCoverageReady : nvis.scriptCoverageMissing}>{described ? 'Described' : 'Needs detail'}</span>
              </div>
              <div style={nvis.scriptCoverageEntity}>{entity}</div>
              <div style={nvis.scriptCoverageText}>{String(row.environment_interaction ?? row.script_evidence ?? row.script_function ?? row.dynamics ?? '')}</div>
              {!described && <div style={nvis.scriptCoverageBlocker}>Reviewer must route this back to script-writer until described or max retries is exceeded.</div>}
              {objects.length > 0 && <div style={nvis.scriptCoverageObjects}>{objects.map((object) => String(object)).join(', ')}</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
