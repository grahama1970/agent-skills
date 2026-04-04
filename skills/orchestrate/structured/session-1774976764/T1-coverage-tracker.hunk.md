# Code Runner Review: T1-coverage-tracker

**Rounds:** 1
**Best score:** 1.000 (round 1)
**DoD passed:** True

## Round Trajectory
| Round | Score | Strategy | Status | Errors |
|-------|-------|----------|--------|--------|
| 1 | 1.000 | direct_fix | keep | 0 (unknown) |

diff --git a/.pi/.worktrees/skills-ci/skills-ci-20260329144123 b/.pi/.worktrees/skills-ci/skills-ci-20260329144123
--- a/.pi/.worktrees/skills-ci/skills-ci-20260329144123
+++ b/.pi/.worktrees/skills-ci/skills-ci-20260329144123
@@ -1 +1 @@
-Subproject commit a8168444f84940f42e2aa90843841352733a7a92
+Subproject commit a8168444f84940f42e2aa90843841352733a7a92-dirty
diff --git a/.pi/.worktrees/skills-ci/skills-ci-20260329144138 b/.pi/.worktrees/skills-ci/skills-ci-20260329144138
--- a/.pi/.worktrees/skills-ci/skills-ci-20260329144138
+++ b/.pi/.worktrees/skills-ci/skills-ci-20260329144138
@@ -1 +1 @@
-Subproject commit a8168444f84940f42e2aa90843841352733a7a92
+Subproject commit a8168444f84940f42e2aa90843841352733a7a92-dirty
diff --git a/.pi/.worktrees/skills-ci/skills-ci-20260329144153 b/.pi/.worktrees/skills-ci/skills-ci-20260329144153
--- a/.pi/.worktrees/skills-ci/skills-ci-20260329144153
+++ b/.pi/.worktrees/skills-ci/skills-ci-20260329144153
@@ -1 +1 @@
-Subproject commit a8168444f84940f42e2aa90843841352733a7a92
+Subproject commit a8168444f84940f42e2aa90843841352733a7a92-dirty
diff --git a/packages/ux-lab/server/index.ts b/packages/ux-lab/server/index.ts
index b01c1c32..f012d3c5 100644
--- a/packages/ux-lab/server/index.ts
+++ b/packages/ux-lab/server/index.ts
@@ -2750,6 +2750,84 @@ app.post('/api/evidence-case/run', async (req, res) => {
   }
 })
 
+// ── Evidence Case Trace: gate chain per control ─────────────────────────────
+
+app.post('/api/evidence-case/trace', async (req, res) => {
+  const { control_id } = req.body as { control_id: string }
+  if (!control_id) return res.status(400).json({ error: 'control_id required' })
+
+  try {
+    const recallResult = await proxyPost('/recall', {
+      q: `${control_id} evidence case verdict`,
+      k: 20,
+      tags: ['sensai-cascade-label'],
+    }) as { items?: Array<Record<string, any>> }
+
+    const cases: Array<Record<string, any>> = []
+    for (const item of recallResult.items ?? []) {
+      let sol: Record<string, any> = {}
+      try { const raw = item.solution ?? ''; if (raw.startsWith('{')) sol = JSON.parse(raw) } catch { continue }
+      const cids: string[] = sol.control_ids ?? []
+      if (!cids.some((c: string) => c === control_id || control_id.startsWith(c) || c.startsWith(control_id))) continue
+      cases.push({
+        verdict: sol.verdict ?? 'unknown', grade: sol.grade ?? '?',
+        question: sol.question ?? item.problem ?? '',
+        gates_passed: sol.gates_passed ?? 0, gates_total: sol.gates_total ?? 0,
+        gate_summary: sol.gate_summary ?? '', tier: sol.tier ?? 'T0', control_ids: cids,
+      })
+    }
+    res.json({ control_id, cases })
+  } catch (e) {
+    res.status(500).json({ error: 'Evidence trace failed', detail: String(e) })
+  }
+})
+
+// ── Critical Path: failing attack chains ────────────────────────────────────
+
+app.post('/api/critical-path', async (req, res) => {
+  const { control_id } = req.body as { control_id?: string }
+
+  try {
+    const q = control_id
+      ? `${control_id} relationship vulnerability attack chain`
+      : 'SPARTA attack chain vulnerability failing not_satisfied'
+    const relResult = await proxyPost('/recall', { q, collections: ['sparta_relationships'], k: 50 }) as { items?: Array<Record<string, any>> }
+    const rels = relResult.items ?? []
+
+    const evidenceResult = await proxyPost('/recall', { q: 'sensai cascade label verdict evidence SPARTA', k: 200, tags: ['sensai-cascade-label'] }) as { items?: Array<Record<string, any>> }
+    const verdictMap = new Map<string, string>()
+    for (const item of evidenceResult.items ?? []) {
+      let sol: Record<string, any> = {}
+      try { const raw = item.solution ?? ''; if (raw.startsWith('{')) sol = JSON.parse(raw) } catch { continue }
+      for (const cid of (sol.control_ids ?? [])) {
+        const existing = verdictMap.get(cid)
+        if (!existing || sol.verdict === 'satisfied') verdictMap.set(cid, sol.verdict ?? 'unknown')
+      }
+    }
+
+    const failingEdges = rels.filter((r: any) => {
+      const sv = verdictMap.get(r.source_control_id) ?? 'none'
+      const tv = verdictMap.get(r.target_control_id) ?? 'none'
+      return sv !== 'satisfied' || tv !== 'satisfied'
+    })
+
+    const nodeMap = new Map<string, { id: string; verdict: string; framework: string }>()
+    const edges: Array<{ source: string; target: string; method: string; score: number }> = []
+    for (const r of failingEdges.slice(0, 30)) {
+      const src = r.source_control_id ?? '', tgt = r.target_control_id ?? ''
+      if (!src || !tgt) continue
+      if (!nodeMap.has(src)) nodeMap.set(src, { id: src, verdict: verdictMap.get(src) ?? 'none', framework: r.source_framework ?? '?' })
+      if (!nodeMap.has(tgt)) nodeMap.set(tgt, { id: tgt, verdict: verdictMap.get(tgt) ?? 'none', framework: r.target_framework ?? '?' })
+      edges.push({ source: src, target: tgt, method: r.method ?? '?', score: r.combined_score ?? 0 })
+    }
+
+    const chains = edges.length > 0 ? [{ nodes: [...nodeMap.values()], edges, severity: edges.length }] : []
+    res.json({ chains, total_failing_edges: failingEdges.length })
+  } catch (e) {
+    res.status(500).json({ error: 'Critical path query failed', detail: String(e) })
+  }
+})
+
 // ── Static file serving for captures/screenshots ────────────────────────────
 app.use('/captures', express.static(CAPTURES_DIR))
 app.use('/screenshots', express.static(SCREENSHOTS_DIR))
diff --git a/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx b/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
index 4114bf61..1aa45ed0 100644
--- a/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
+++ b/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
@@ -1,5 +1,6 @@
 import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
 import { Shield, Workflow, Trash2, Code, Layers, MessageSquare, Network, Search, History, Table2, Undo, Redo, GitGraph, List } from 'lucide-react'
+import { useRegisterAction } from '../../hooks/useRegisterAction'
 import { EMBRY } from '../common/EmbryStyle'
 import { LeftPane, LeftPaneSection, paneItemStyle, useLeftPaneSearch } from '../common/LeftPane'
 import { ContextMenu } from '../common/ContextMenu'
@@ -200,6 +201,18 @@ export function BinaryExplorerView() {
   const [chatInput, setChatInput] = useState('')
   const [chatLoading, setChatLoading] = useState(false)
 
+  // --- Register UI actions for QuerySpec pipeline (voice/chat → deterministic execution) ---
+  const APP = 'binary-explorer'
+  useRegisterAction('be-select-node', { app: APP, action: 'SELECT_NODE', label: 'Select Node', description: 'Click a node to select it and show its details', params: { requires_entity: true } })
+  useRegisterAction('be-expand-node', { app: APP, action: 'EXPAND', label: 'Expand Node', description: 'Expand a node to show its neighbors', params: { requires_entity: true, hops: 1 } })
+  useRegisterAction('be-zoom-in', { app: APP, action: 'ZOOM_IN', label: 'Zoom In', description: 'Zoom into the graph to see more detail' })
+  useRegisterAction('be-zoom-out', { app: APP, action: 'ZOOM_OUT', label: 'Zoom Out', description: 'Zoom out of the graph to see the full picture' })
+  useRegisterAction('be-view-all', { app: APP, action: 'VIEW_ALL', label: 'Show All Nodes', description: 'Show all nodes in the binary, view all features' })
+  useRegisterAction('be-set-perspective', { app: APP, action: 'SET_PERSPECTIVE', label: 'Set Perspective', description: 'Switch graph perspective view filter', params: { perspective: 'security' } })
+  useRegisterAction('be-dismiss-node', { app: APP, action: 'DISMISS_NODE', label: 'Dismiss Node', description: 'Remove a node from the scene', params: { requires_entity: true } })
+  useRegisterAction('be-toggle-progressive', { app: APP, action: 'TOGGLE_PROGRESSIVE', label: 'Toggle Progressive', description: 'Toggle progressive disclosure mode on or off' })
+  useRegisterAction('be-focus-cluster', { app: APP, action: 'FOCUS_CLUSTER', label: 'Focus Cluster', description: 'Focus on a cluster of related nodes', params: { requires_entity: true } })
+
   // --- Graph Visual State ---
   const [viewMode, setViewMode] = useState<'graph' | 'tree'>('graph')
   const [layoutMode, setLayoutMode] = useState<'organic' | 'stratified' | 'clustered'>('organic')