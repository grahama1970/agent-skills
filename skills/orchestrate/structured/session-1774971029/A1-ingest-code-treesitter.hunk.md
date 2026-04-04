# Code Runner Review: A1-ingest-code-treesitter

**Rounds:** 1
**Best score:** 0.985 (round 1)
**DoD passed:** True

## Round Trajectory
| Round | Score | Strategy | Status | Errors |
|-------|-------|----------|--------|--------|
| 1 | 0.985 | direct_fix | keep | 0 (unknown) |

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
index 81b5d95a..0bd32c08 100644
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
@@ -110,29 +112,72 @@ def strategy_search_huggingface(project_dir: Path, meta: dict, existing_labels:
         for ds_info in found_datasets[:3]:
             try:
                 from datasets import load_dataset
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
+                # Try multiple splits — some datasets don't have "train"
+                ds = None
+                hf_token = os.environ.get("HF_TOKEN", "")
+                for try_split in ["train", "validation", "test"]:
+                    try:
+                        ds = load_dataset(ds_info["id"], split=try_split, token=hf_token or None, trust_remote_code=False)
+                        logger.info(f"  {ds_info['id']}: loaded {try_split} split ({len(ds)} rows)")
+                        break
+                    except Exception:
+                        continue
+                if ds is None:
+                    logger.warning(f"  {ds_info['id']}: no loadable split found")
+                    continue
+                # Find text and label fields — datasets use different names
+                text_field = None
+                for f in ["text", "sms", "sentence", "content", "review", "message", "input"]:
+                    if f in ds.features:
+                        text_field = f
+                        break
+                label_field = None
+                # Prefer string label fields over integer ones
+                for f in ["sentiment", "class", "category", "label", "labels"]:
+                    if f in ds.features:
+                        label_field = f
+                        break
+
+                if not text_field or not label_field:
+                    logger.info(f"  {ds_info['id']}: no text/label fields — features: {list(ds.features.keys())}")
+                    continue
+
+                # Build label mapping — HF ClassLabel uses integers with .names
+                label_map: dict[str, str] = {}
+                existing_lower = {l.lower(): l for l in existing_labels}
+
+                if hasattr(ds.features.get(label_field), "names"):
+                    hf_names = ds.features[label_field].names
+                    logger.info(f"  {ds_info['id']}: ClassLabel names: {hf_names}")
+                    for i, name in enumerate(hf_names):
+                        if name.lower() in existing_lower:
+                            label_map[str(i)] = existing_lower[name.lower()]
+                else:
+                    # Direct string labels — case-insensitive match
+                    sample_labels = set(str(row[label_field]) for row in ds.select(range(min(100, len(ds)))))
+                    for sl in sample_labels:
+                        if sl.lower() in existing_lower:
+                            label_map[sl] = existing_lower[sl.lower()]
+
+                if not label_map:
+                    logger.info(f"  {ds_info['id']}: no matching labels")
+                    continue
+
+                logger.info(f"  {ds_info['id']}: label map: {label_map}")
+
+                # Extract matching samples
+                count = 0
+                for row in ds:
+                    text = row[text_field]
+                    if not text or not isinstance(text, str) or len(text.strip()) < 5:
+                        continue
+                    raw = str(row[label_field])
+                    if raw in label_map:
+                        new_samples.append({"text": text.strip()[:1000], "class": label_map[raw], "split": "train", "_source": ds_info["id"]})
+                        count += 1
+                if count:
+                    logger.info(f"  {ds_info['id']}: extracted {count} samples")
+                    break  # got data from one source, stop
             except Exception as e:
                 logger.warning(f"  Failed to load {ds_info['id']}: {e}")
 
diff --git a/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx b/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
index 73116d2e..800f234b 100644
--- a/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
+++ b/packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx
@@ -1185,9 +1185,14 @@ export function BinaryExplorerView() {
     const pipelineStart = performance.now()
 
     // Timed fetch wrapper — enforces per-stage timeout + abort signal
+    // Per-stage timeout — each fetch gets its own AbortController so one timeout doesn't kill the pipeline
     const timedFetch = (url: string, init: RequestInit, budgetMs: number): Promise<Response> => {
-      const timeout = setTimeout(() => abortCtl.abort(), budgetMs)
-      return fetch(url, { ...init, signal }).finally(() => clearTimeout(timeout))
+      const stageCtl = new AbortController()
+      const onPipelineAbort = () => stageCtl.abort()
+      signal.addEventListener('abort', onPipelineAbort, { once: true })
+      const timeout = setTimeout(() => stageCtl.abort(), budgetMs)
+      return fetch(url, { ...init, signal: stageCtl.signal })
+        .finally(() => { clearTimeout(timeout); signal.removeEventListener('abort', onPipelineAbort) })
     }
 
     try {
@@ -1199,7 +1204,7 @@ export function BinaryExplorerView() {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({ text, collection: 'binary_features' }),
-        }, 500)
+        }, 3000)
         if (!res.ok) throw new Error(`extract-entities API returned ${res.status}`)
         const { entities } = await res.json()
         mentionedEntities.push(...(entities ?? []).map((e: { id: string; name: string; label: string; type: string }) => ({
diff --git a/packages/ux-lab/src/components/embry-terminal/EmbryTerminalView.tsx b/packages/ux-lab/src/components/embry-terminal/EmbryTerminalView.tsx
index ab23d7f0..a6c74299 100644
--- a/packages/ux-lab/src/components/embry-terminal/EmbryTerminalView.tsx
+++ b/packages/ux-lab/src/components/embry-terminal/EmbryTerminalView.tsx
@@ -266,7 +266,7 @@ const MessageItem = memo(function MessageItem({ msg }: { msg: Message }) {
           background: '#1e1e24', fontSize: 15, lineHeight: 1.65, color: '#e2e8f0',
           fontFamily: 'var(--font-ui)',
         }}>
-          {msg.content}
+          {highlightSkills(msg.content)}
         </div>
       </div>
     );