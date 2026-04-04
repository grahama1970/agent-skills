# Code Runner Review: A1-ingest-code-treesitter

**Rounds:** 3
**Best score:** 0.490 (round 1)
**DoD passed:** False

## Round Trajectory
| Round | Score | Strategy | Status | Errors |
|-------|-------|----------|--------|--------|
| 1 | 0.490 | direct_fix | keep | 0 (unknown) |
| 2 | 0.490 | structured_analysis | discard | 0 (unknown) |
| 3 | 0.490 | simplify | discard | 0 (unknown) |

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
index 60a542b7..8cd4d11d 100644
--- a/packages/ux-lab/server/index.ts
+++ b/packages/ux-lab/server/index.ts
@@ -1974,9 +1974,16 @@ app.get('/api/projects/classifier-lab/research/:id', async (req, res) => {
       } catch { /* skip */ }
     }
 
+    // If no research exists, provide a starting prompt
+    if (!markdown && timeline.length === 0) {
+      const meta = existsSync(resolve(CLASSIFIER_DIR, projectId, 'meta.json'))
+        ? JSON.parse(await readFile(resolve(CLASSIFIER_DIR, projectId, 'meta.json'), 'utf-8'))
+        : {}
+      markdown = `# ${meta.name || projectId}\n\n**No research yet.** The project agent needs to run /dogpile to research:\n\n- What backbone models work for this task?\n- What datasets are available?\n- What hyperparameters are recommended?\n- What F1 should we target?\n\nThis will populate the Research tab with findings and seed the Tune tab with initial settings.`
+    }
     res.json({ markdown, source: markdown ? 'disk' : null, timeline, nextStepsQuery })
   } catch {
-    res.json({ markdown: null, timeline: [], nextStepsQuery: null })
+    res.json({ markdown: '# Research\n\nNo research data available. Run /dogpile to start.', timeline: [], nextStepsQuery: null })
   }
 })
 
@@ -2020,6 +2027,31 @@ app.get('/api/projects/classifier-lab/gpu-info', async (_req, res) => {
   }
 })
 
+// Train results — reads from benchmark.json results array
+app.get('/api/projects/classifier-lab/train-results/:id', async (req, res) => {
+  try {
+    const benchPath = resolve(CLASSIFIER_DIR, req.params.id, 'benchmark.json')
+    if (existsSync(benchPath)) {
+      const bench = JSON.parse(await readFile(benchPath, 'utf-8'))
+      const results = (bench.results || []).map((r: any, i: number) => ({
+        rank: i + 1,
+        backbone: r.backbone || 'unknown',
+        lr: r.lr || '—',
+        bs: r.batch_size || 0,
+        f1: r.macro_f1 || r.f1 || 0,
+        acc: r.accuracy || 0,
+        latency: r.latency || '—',
+        cost: r.cost || 'FREE',
+        status: (r.macro_f1 || r.f1 || 0) >= (bench.gate_f1 || 0.90) ? 'pass' as const : 'fail' as const,
+      }))
+      return res.json(results)
+    }
+    res.json([])
+  } catch {
+    res.json([])
+  }
+})
+
 app.get('/api/projects/classifier-lab/tune-results/:id', async (req, res) => {
   const projectId = req.params.id
   try {
diff --git a/packages/ux-lab/src/components/embry-terminal/EmbryTerminalView.tsx b/packages/ux-lab/src/components/embry-terminal/EmbryTerminalView.tsx
index dce3223a..3e15f6f3 100644
--- a/packages/ux-lab/src/components/embry-terminal/EmbryTerminalView.tsx
+++ b/packages/ux-lab/src/components/embry-terminal/EmbryTerminalView.tsx
@@ -114,16 +114,19 @@ const BACKEND_URL = import.meta.env.DEV
   ? 'http://127.0.0.1:8640/api'
   : '/embry-terminal/api';
 
+const DEV_TOKEN = 'embry-dev-token';
+const AUTH_HEADERS: HeadersInit = { 'Authorization': `Bearer ${DEV_TOKEN}` };
+
 // ── API ─────────────────────────────────────────────────────────────────────
 
 async function fetchProjects(): Promise<Project[]> {
-  const res = await fetch(`${BACKEND_URL}/projects`);
+  const res = await fetch(`${BACKEND_URL}/projects`, { headers: AUTH_HEADERS });
   if (!res.ok) return [];
   return res.json();
 }
 
 async function fetchSkills(): Promise<Skill[]> {
-  const res = await fetch(`${BACKEND_URL}/skills`);
+  const res = await fetch(`${BACKEND_URL}/skills`, { headers: AUTH_HEADERS });
   if (!res.ok) return [];
   return res.json();
 }
@@ -517,7 +520,7 @@ export function EmbryTerminalView() {
     try {
       const recallRes = await fetch(`${BACKEND_URL}/agent/recall`, {
         method: 'POST',
-        headers: { 'Content-Type': 'application/json' },
+        headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
         body: JSON.stringify({ query: text, project: activeProject?.name }),
       });
       if (recallRes.ok) {
@@ -549,7 +552,7 @@ export function EmbryTerminalView() {
         // SSE streaming for skill execution
         const res = await fetch(`${BACKEND_URL}/agent/message`, {
           method: 'POST',
-          headers: { 'Content-Type': 'application/json' },
+          headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
           body: JSON.stringify({ message: text, backend: 'skill', skill: skillMatch![1], project: activeProject?.name }),
         });
         const reader = res.body?.getReader();
@@ -580,7 +583,7 @@ export function EmbryTerminalView() {
         // Non-streaming scillm call
         const res = await fetch(`${BACKEND_URL}/agent/message`, {
           method: 'POST',
-          headers: { 'Content-Type': 'application/json' },
+          headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
           body: JSON.stringify({ message: text, backend: 'scillm', model: 'text', project: activeProject?.name }),
         });
         const data = await res.json();
diff --git a/packages/ux-lab/src/components/sparta/explorer/ClassifierLabView.tsx b/packages/ux-lab/src/components/sparta/explorer/ClassifierLabView.tsx
index ae2c445a..f7310458 100644
--- a/packages/ux-lab/src/components/sparta/explorer/ClassifierLabView.tsx
+++ b/packages/ux-lab/src/components/sparta/explorer/ClassifierLabView.tsx
@@ -184,10 +184,10 @@ function computePreflights(
       blocker: 'Fix data issues in Data tab first',
     })
     checks.push({
-      check: 'Tune config exists',
-      passed: !!tuneConfig && Object.keys(tuneConfig).length > 1,
-      detail: tuneConfig?.lr ? `LR=${tuneConfig.lr}, epochs=${tuneConfig.epochs}` : 'No config',
-      blocker: 'Configure hyperparameters in Tune tab',
+      check: 'Tune config set by agent or human (not defaults)',
+      passed: !!tuneConfig && tuneConfig._source && tuneConfig._source !== 'default' && !tuneConfig._source?.startsWith('default-'),
+      detail: tuneConfig?._source ? `Source: ${tuneConfig._source}` : 'Not configured',
+      blocker: 'Run /dogpile research first — it sets initial HP recommendations. Or configure manually in Tune tab.',
     })
   }