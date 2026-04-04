# Code Runner Review: B1-replace-subagent-dispatch

**Rounds:** 2
**Best score:** 1.000 (round 2)
**DoD passed:** True

## Round Trajectory
| Round | Score | Strategy | Status | Errors |
|-------|-------|----------|--------|--------|
| 1 | 0.485 | direct_fix | keep | 0 (unknown) |
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
diff --git a/.pi/skills/classifier-lab/scripts/data_enrichment.py b/.pi/skills/classifier-lab/scripts/data_enrichment.py
index 81b5d95a..e73acc30 100644
--- a/.pi/skills/classifier-lab/scripts/data_enrichment.py
+++ b/.pi/skills/classifier-lab/scripts/data_enrichment.py
@@ -52,11 +52,13 @@ def check_sufficiency(samples: list[dict], min_per_class: int) -> dict:
     train = [s for s in samples if s.get("split", "train") == "train"]
     label_counts: Counter[str] = Counter()
     for s in train:
-        labels = s.get("labels", [])
-        if isinstance(labels, list):
+        labels = s.get("labels")
+        if isinstance(labels, list) and labels:
             label_counts.update(labels)
         else:
-            label_counts[s.get("class", s.get("className", "unknown"))] += 1
+            lbl = s.get("class", s.get("className", s.get("label", "")))
+            if lbl:
+                label_counts[str(lbl)] += 1
 
     num_classes = len(label_counts)
     total_train = len(train)
@@ -105,36 +107,82 @@ def strategy_search_huggingface(project_dir: Path, meta: dict, existing_labels:
             logger.info("  No matching datasets found on HuggingFace")
             return []
 
-        # Try to load top dataset and check if labels map
+        # Try to load datasets, map labels, extract samples
+        from datasets import load_dataset
+
+        hf_token = os.environ.get("HF_TOKEN", "")
+        existing_lower = {l.lower(): l for l in existing_labels}
         new_samples: list[dict] = []
-        for ds_info in found_datasets[:3]:
+
+        for ds_info in found_datasets[:8]:
+            if new_samples:
+                break  # got data, stop
             try:
-                from datasets import load_dataset
-                ds = load_dataset(ds_info["id"], split="train", trust_remote_code=False)
-                # Check if it has text + labels that overlap with our labels
-                if "text" in ds.features and ("label" in ds.features or "labels" in ds.features):
-                    label_field = "labels" if "labels" in ds.features else "label"
-                    ds_labels = set()
-                    for row in ds:
-                        lbl = row[label_field]
-                        if isinstance(lbl, list):
-                            ds_labels.update(lbl)
-                        else:
-                            ds_labels.add(str(lbl))
-
-                    overlap = ds_labels & existing_labels
-                    if overlap:
-                        logger.info(f"  {ds_info['id']}: {len(overlap)} overlapping labels")
-                        for row in ds:
-                            lbl = row[label_field]
-                            labels = lbl if isinstance(lbl, list) else [str(lbl)]
-                            mapped = [l for l in labels if l in existing_labels]
-                            if mapped:
-                                new_samples.append({"text": row["text"], "labels": mapped, "split": "train", "_source": ds_info["id"]})
-                    else:
-                        logger.info(f"  {ds_info['id']}: 0 overlapping labels — skipping")
+                # Try multiple splits
+                loaded = None
+                for try_split in ["train", "validation", "test"]:
+                    try:
+                        loaded = load_dataset(ds_info["id"], split=try_split, token=hf_token or None, trust_remote_code=False)
+                        logger.info(f"  {ds_info['id']}: loaded {try_split} ({len(loaded)} rows)")
+                        break
+                    except Exception:
+                        continue
+                if loaded is None:
+                    continue
+
+                # Find text field
+                text_field = None
+                for f in ["text", "sms", "sentence", "content", "reviewText", "review", "message", "input"]:
+                    if f in loaded.features:
+                        text_field = f
+                        break
+
+                # Find label field — prefer string fields over integers
+                label_field = None
+                for f in ["sentiment", "class", "category", "label", "labels"]:
+                    if f in loaded.features:
+                        label_field = f
+                        break
+
+                if not text_field or not label_field:
+                    logger.info(f"  {ds_info['id']}: no text/label fields — {list(loaded.features.keys())}")
+                    continue
+
+                # Map labels — handle ClassLabel (int→name) and direct strings
+                label_map: dict[str, str] = {}
+                feat = loaded.features.get(label_field)
+                if hasattr(feat, "names"):
+                    for i, name in enumerate(feat.names):
+                        if name.lower() in existing_lower:
+                            label_map[str(i)] = existing_lower[name.lower()]
+                    if label_map:
+                        logger.info(f"  {ds_info['id']}: ClassLabel map: {label_map}")
+                else:
+                    sample_labels = {str(row[label_field]) for row in loaded.select(range(min(100, len(loaded))))}
+                    for sl in sample_labels:
+                        if sl.lower() in existing_lower:
+                            label_map[sl] = existing_lower[sl.lower()]
+                    if label_map:
+                        logger.info(f"  {ds_info['id']}: string label map: {label_map}")
+
+                if not label_map:
+                    logger.info(f"  {ds_info['id']}: no label match")
+                    continue
+
+                # Extract
+                count = 0
+                for row in loaded:
+                    text = row[text_field]
+                    if not isinstance(text, str) or len(text.strip()) < 5:
+                        continue
+                    raw = str(row[label_field])
+                    if raw in label_map:
+                        new_samples.append({"text": text.strip()[:1000], "class": label_map[raw], "split": "train", "_source": ds_info["id"]})
+                        count += 1
+                logger.info(f"  {ds_info['id']}: extracted {count} samples")
+
             except Exception as e:
-                logger.warning(f"  Failed to load {ds_info['id']}: {e}")
+                logger.warning(f"  {ds_info['id']}: failed — {e}")
 
         logger.info(f"  HuggingFace enrichment: {len(new_samples)} new samples")
         return new_samples
@@ -218,9 +266,13 @@ def enrich(
     # Get existing labels
     existing_labels: set[str] = set()
     for s in samples:
-        labels = s.get("labels", [])
-        if isinstance(labels, list):
+        labels = s.get("labels")
+        if isinstance(labels, list) and labels:
             existing_labels.update(labels)
+        else:
+            lbl = s.get("class", s.get("className", s.get("label", "")))
+            if lbl:
+                existing_labels.add(str(lbl))
 
     # Pre-check
     status = check_sufficiency(samples, min_per_class)
diff --git a/.pi/skills/create-classifier/projects/sentiment-analysis/meta.json b/.pi/skills/create-classifier/projects/sentiment-analysis/meta.json
new file mode 100644
index 00000000..28841ab7
--- /dev/null
+++ b/.pi/skills/create-classifier/projects/sentiment-analysis/meta.json
@@ -0,0 +1,15 @@
+{
+  "name": "sentiment-analysis",
+  "status": "data-enriched",
+  "modality": "text",
+  "samples": 15,
+  "classes": 3,
+  "enrichment_attempts": [
+    {
+      "strategy": "huggingface",
+      "tried": true,
+      "new_samples": 31155,
+      "iteration": 1
+    }
+  ]
+}
\ No newline at end of file
diff --git a/packages/ux-lab/src/components/sparta/explorer/ChatTab.tsx b/packages/ux-lab/src/components/sparta/explorer/ChatTab.tsx
index 5c377f18..a07ebee7 100644
--- a/packages/ux-lab/src/components/sparta/explorer/ChatTab.tsx
+++ b/packages/ux-lab/src/components/sparta/explorer/ChatTab.tsx
@@ -341,18 +341,48 @@ export function ChatTab() {
     focusControl, setFocusControl, currentSystem, setCurrentSystem,
   }
 
+  // ── Resizable pane ──────────────────────────────────────────────────
+
+  const [chatWidth, setChatWidth] = useState(450)
+  const dragging = useRef(false)
+  const dragStartX = useRef(0)
+  const dragStartW = useRef(450)
+
+  const onDragStart = useCallback((e: React.MouseEvent) => {
+    e.preventDefault()
+    dragging.current = true
+    dragStartX.current = e.clientX
+    dragStartW.current = chatWidth
+
+    const onMove = (ev: MouseEvent) => {
+      if (!dragging.current) return
+      const delta = ev.clientX - dragStartX.current
+      setChatWidth(Math.max(280, Math.min(800, dragStartW.current + delta)))
+    }
+    const onUp = () => {
+      dragging.current = false
+      document.removeEventListener('mousemove', onMove)
+      document.removeEventListener('mouseup', onUp)
+      document.body.style.cursor = ''
+      document.body.style.userSelect = ''
+    }
+    document.addEventListener('mousemove', onMove)
+    document.addEventListener('mouseup', onUp)
+    document.body.style.cursor = 'col-resize'
+    document.body.style.userSelect = 'none'
+  }, [chatWidth])
+
   // ── Render ─────────────────────────────────────────────────────────
 
   return (
     <ChatTabContext.Provider value={ctxValue}>
       <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
 
-        {/* LEFT: Chat pane (450px) */}
+        {/* LEFT: Chat pane (resizable) */}
         <div style={{
-          width: 450, minWidth: 450, maxWidth: 450,
+          width: chatWidth, minWidth: 280, maxWidth: 800,
           display: 'flex', flexDirection: 'column',
-          borderRight: `1px solid ${EMBRY.border}`,
-          backgroundColor: EMBRY.bg,
+          backgroundColor: EMBRY.bg, flexShrink: 0,
         }}>
           {/* Scope + system selector */}
           <div style={{
@@ -391,8 +421,20 @@ export function ChatTab() {
           </div>
         </div>
 
+        {/* DRAG HANDLE */}
+        <div
+          onMouseDown={onDragStart}
+          style={{
+            width: 5, cursor: 'col-resize', flexShrink: 0,
+            background: dragging.current ? EMBRY.accent : EMBRY.border,
+            transition: dragging.current ? 'none' : 'background 0.15s',
+          }}
+          onMouseEnter={(e) => { if (!dragging.current) e.currentTarget.style.background = EMBRY.accent }}
+          onMouseLeave={(e) => { if (!dragging.current) e.currentTarget.style.background = EMBRY.border }}
+        />
+
         {/* RIGHT: Visualization workspace (flex) */}
-        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
+        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
 
           {/* Viz mode toggle */}
           <div style={{
@@ -428,13 +470,13 @@ export function ChatTab() {
           <div style={{ flex: 1, overflow: 'hidden' }}>
             {vizMode === 'matrix' ? (
               <ThreatMatrix.Provider state={matrixState} actions={matrixActions} meta={matrixMeta}>
-                <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
+                <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', position: 'relative' }}>
                   <ThreatMatrix.Header />
                   <ThreatMatrix.TacticStrip />
-                  <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
+                  <div style={{ flex: 1, overflow: 'hidden' }}>
                     <ThreatMatrix.Grid />
-                    <ThreatMatrix.Detail />
                   </div>
+                  <ThreatMatrix.Detail />
                 </div>
               </ThreatMatrix.Provider>
             ) : (
diff --git a/packages/ux-lab/src/components/sparta/shared/ThreatMatrix.tsx b/packages/ux-lab/src/components/sparta/shared/ThreatMatrix.tsx
index 7b463c4c..5dd7a4b7 100644
--- a/packages/ux-lab/src/components/sparta/shared/ThreatMatrix.tsx
+++ b/packages/ux-lab/src/components/sparta/shared/ThreatMatrix.tsx
@@ -223,17 +223,19 @@ function TacticStrip() {
         const s = stats[tactic.name] ?? { total: 0, covered: 0, partial: 0, gap: 0 }
         const pct = s.total > 0 ? Math.round((s.covered / s.total) * 100) : 0
         return (
-          <div key={tactic.id} style={{ flex: 1, minWidth: 100, padding: '8px 10px', borderRight: `1px solid ${EMBRY.border}`, textAlign: 'center' }}>
+          <div key={tactic.id} style={{ flex: 1, minWidth: 100, padding: '8px 10px', borderRight: `1px solid ${EMBRY.border}`, textAlign: 'center', display: 'flex', flexDirection: 'column' }}>
             <div style={{ fontSize: 9, fontWeight: 700, color: EMBRY.white, marginBottom: 2 }}>{tactic.name}</div>
             <div style={{ fontSize: 8, color: EMBRY.dim }}>{tactic.prefix} · {s.total} tech</div>
-            <div style={{ display: 'flex', height: 3, borderRadius: 2, overflow: 'hidden', marginTop: 4 }}>
-              {s.total > 0 && <>
-                <div style={{ width: `${(s.covered / s.total) * 100}%`, backgroundColor: EMBRY.green }} />
-                <div style={{ width: `${(s.partial / s.total) * 100}%`, backgroundColor: EMBRY.amber }} />
-                <div style={{ width: `${(s.gap / s.total) * 100}%`, backgroundColor: EMBRY.red }} />
-              </>}
+            <div style={{ marginTop: 'auto' }}>
+              <div style={{ display: 'flex', height: 3, borderRadius: 2, overflow: 'hidden', marginTop: 4 }}>
+                {s.total > 0 && <>
+                  <div style={{ width: `${(s.covered / s.total) * 100}%`, backgroundColor: EMBRY.green }} />
+                  <div style={{ width: `${(s.partial / s.total) * 100}%`, backgroundColor: EMBRY.amber }} />
+                  <div style={{ width: `${(s.gap / s.total) * 100}%`, backgroundColor: EMBRY.red }} />
+                </>}
+              </div>
+              <div style={{ fontSize: 8, color: pct === 100 ? EMBRY.green : EMBRY.dim, marginTop: 2 }}>{pct}%</div>
             </div>
-            <div style={{ fontSize: 8, color: pct === 100 ? EMBRY.green : EMBRY.dim, marginTop: 2 }}>{pct}%</div>
           </div>
         )
       })}
@@ -345,8 +347,10 @@ function Detail() {
 
   return (
     <div style={{
-      width: 400, flexShrink: 0, backgroundColor: EMBRY.bgPanel,
+      position: 'absolute', top: 0, right: 0, bottom: 0,
+      width: 420, backgroundColor: EMBRY.bgPanel,
       borderLeft: `1px solid ${EMBRY.border}`, overflow: 'auto', display: 'flex', flexDirection: 'column',
+      zIndex: 10, boxShadow: '-4px 0 20px rgba(0,0,0,0.4)',
     }}>
       {/* Header */}
       <div style={{ padding: '16px 20px', borderBottom: `1px solid ${EMBRY.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>