# Code Runner Review: S1-wire-security-scan

**Rounds:** 2
**Best score:** 1.000 (round 2)
**DoD passed:** True

## Round Trajectory
| Round | Score | Strategy | Status | Errors |
|-------|-------|----------|--------|--------|
| 1 | 0.490 | direct_fix | keep | 0 (unknown) |
| 2 | 1.000 | structured_analysis | keep | 0 (unknown) |

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
diff --git a/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx b/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
index 4114bf61..bcdcc2dc 100644
--- a/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
+++ b/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
@@ -1249,17 +1249,17 @@ export function BinaryExplorerView() {
       let intentData: QuerySpec | null = null
       const trace: PipelineTrace = { entities: mentionedEntities, candidates: [], source: 'none', reason: '' }
 
-      // Step 1: Recall candidate actions from app_actions (works with or without entities)
+      // Step 1: Recall candidate actions from app_actions via /search-collection (BM25 only, no cross-collection blending)
       type CandidateAction = { _key: string, ui_action: string, params: Record<string, string>, description: string, score: number }
       const candidates: CandidateAction[] = []
       try {
-        const actionsRes = await timedFetch(`${API}/api/memory/recall`, {
+        const actionsRes = await timedFetch(`${API}/api/memory/search-collection`, {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({
             q: entityCtx ? `${text} ${entityCtx}` : text,
-            k: 5, scope: 'binary-explorer',
-            collections: ['app_actions'], tags: ['queryspec-action'],
+            collection: 'app_actions',
+            k: 5,
           }),
         }, 500)
         if (actionsRes.ok) {
@@ -1274,7 +1274,7 @@ export function BinaryExplorerView() {
                   ui_action: parsed.ui_action,
                   params: parsed.params ?? {},
                   description: item.problem ?? '',
-                  score: item.scores?.bm25 ?? 0,
+                  score: item._score ?? 0,
                 })
               }
             } catch {