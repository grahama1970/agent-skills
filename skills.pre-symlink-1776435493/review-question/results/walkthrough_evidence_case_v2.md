# evidence_case.py v2: Honest Walkthrough

**Date:** 2026-03-03
**File:** `pi-mono/.pi/skills/review-question/evidence_case.py`
**Status:** Partially tested (1 question verified, 50-question bank NOT run)
**Reviewed by:** Brandon Bailey consultation SKIPPED (machine at load 229, swap 100%)
**User concerns:** Entity extraction correctness, zero regex, fallback reliability, F36 detection

---

## Why Previous Versions Failed

### Failure 1: Datalake short-circuit blocked Gates 3-5
**What we did:** Gate 6 (datalake connection) failing caused an early return at lines 996-1001 that classified as `DATALAKE_NOT_CONNECTED` BEFORE Gates 3-5 ran.
**Why it failed:** Gate 5 populates `total_qras`. Early return = 0 QRAs even when 979 existed.

### Failure 2: `/memory recall` doesn't expose `control_id`
**What we did:** Used `/memory recall` to verify entities, checking `control_id` on each returned item.
**Why it failed:** Recall items from `lessons` collection don't have `control_id` at top level — all returned `N/A`.

### Failure 3: F36 "INS" substring match
**What we did:** Used `if phrase.strip() in q_lower` for F36 category keyword detection.
**Why it failed:** "ins" (Inertial Navigation System) matched inside "agaINSt", causing false `01_avionics` categorization for pure SPARTA questions.

### Failure 4: Classification logic triggered on wrong F36 source
**What we did:** `_classify` function used `f36_categories` populated from recall results.
**Why it failed:** Should only trigger `DATALAKE_NOT_CONNECTED` from Gate 1's original query spec F36 categories, not from downstream recall.

### Failure 5: Regex kept coming back
**What we did:** Each "fix" replaced one regex hack with another — word-boundary regex, `re.split` tokenization, `re.findall` for word extraction.
**Why it failed:** User instruction is NON-NEGOTIABLE: no regex, no string matching. ArangoDB is the only source of truth.

---

## What v2 Changes

### Change 1: Removed `import re` entirely

**Before:** `import re` + 4 regex usages (`_SAFE_ENTITY_RE`, `re.split`, `re.findall`, `re.search`)
**After:** Zero regex. `_SAFE_ENTITY_CHARS` is a character set for sanitization (line 46).

**What this fixes:** Failure 3 and 5 — no more string-based entity/category detection.
**What could still go wrong:** The `_sanitize_entity_id` function uses `all(c in set for c in eid)` — this is O(n) per character but entity IDs are short (<30 chars), so performance is fine.
**Honest risk level:** LOW — this is a pure deletion, less code = fewer bugs.

### Change 2: `_memory_recall` uses `--scope` not `--collections` (line 91-99)

**Before:** Wrapper passed `--collections` flag which the recall CLI doesn't accept.
**After:** Uses `--scope` (which is a real parameter) and returns `items` key first.

**What this fixes:** The recall wrapper was silently failing because `--collections` was ignored.
**What could still go wrong:** If the `recall` CLI changes its JSON output format (e.g., removes `items` key), the wrapper would return an empty list silently.
**Honest risk level:** LOW — the CLI has been stable and we fall back to `results` key.

### Change 3: `_db_entity_extract` uses recall + title parsing (lines 226-284)

**Before:** Tokenized question with `re.split`, applied heuristics (`has_alpha`, `has_digit`), then verified each token against `sparta_controls`.
**After:** Calls `/memory recall --scope sparta --k 20`, extracts control IDs from lesson titles ("What is SV-MA-3: ..."), verifies each against `sparta_controls` via `/memory count`.

**What this fixes:** Failures 2 and 5 — no regex, database does the semantic matching.
**What could still go wrong:**
- **MEDIUM RISK:** Title parsing assumes "What is X: ..." format. If QRA titles don't follow this convention, control IDs won't be extracted. TESTED: current titles DO follow this format, but future QRAs might not.
- **MEDIUM RISK:** Semantic recall may return UNRELATED controls. When asked about "SV-MA-3", recall returned SV-MA-1, SV-MA-5, SV-MA-6, SV-MA-7, EX-0012.08, SV-AV-4, SMSR-5 — semantically related but not what the question asked about. The verify step catches this (they all exist), but the evidence case now contains 8 entities instead of 1.
- **LOW RISK:** Each entity verification is a separate `/memory count` subprocess call. 20 recall results = up to 20 subprocess spawns. On a healthy machine this takes <5s total. On a machine at load 229, it could timeout.
**Honest risk level:** MEDIUM — the title-parsing assumption is fragile.

### Change 4: F36 category detection via `scope=datalake` recall (lines 266-276)

**Before:** Regex keyword matching against F36_CATEGORIES descriptions + hardcoded `f36_context_terms` list.
**After:** Calls `/memory recall --scope datalake --k 5`, checks item tags for F36 category IDs.

**What this fixes:** Failures 3 and 5 — no keyword lists, database decides.
**What could still go wrong:**
- **HIGH RISK — UNTESTED:** `scope=datalake` has NEVER been tested. I don't know if any lessons have `scope=datalake`. If no datalake-scoped lessons exist, F36 detection silently returns empty. This means pure F36 questions (no SPARTA control IDs) would classify as NEEDS_CLARIFICATION instead of being routed to the datalake.
- **MEDIUM RISK:** Even if datalake lessons exist, their `tags` field may not contain F36 category IDs like `01_avionics`. The tag format assumption is unverified.
**Honest risk level:** HIGH — this is aspirational code that has not been tested against real data.

### Change 5: Datalake short-circuit removed (previous session)

**Before:** Lines 996-1001 returned early with `DATALAKE_NOT_CONNECTED` when Gate 6 failed.
**After:** Gate 6 failure is informational — Gates 3-5 always run.

**What this fixes:** Failure 1 — pure SPARTA questions now always get QRA counts.
**What could still go wrong:** Nothing meaningful — this was a pure bug fix.
**Honest risk level:** LOW — tested and confirmed working (EC-G27: DECOMPOSE, 1019 QRAs).

### Change 6: Classification uses Gate 1 F36 categories only (previous session)

**Before:** `_classify` checked `f36_categories` populated from recall results.
**After:** Checks `gate1.details.get("f36_categories", [])` — only Gate 1's original detection matters.

**What this fixes:** Failure 4 — prevents false DATALAKE_NOT_CONNECTED for pure SPARTA questions.
**What could still go wrong:** If Gate 1 itself misdetects F36 categories (via the now-recall-based detection), the same problem returns at the classification stage.
**Honest risk level:** LOW — tested and confirmed working.

### Change 7: `/memory intent` timeout reduced to 10s (previous session)

**Before:** 30s timeout.
**After:** 10s timeout, falls back to `_db_entity_extract`.

**What this fixes:** Reduced per-question latency from 50-80s to ~20s.
**What could still go wrong:** If the intent service is slow but would succeed at 15s, we'd fall back unnecessarily. Fallback quality is different (semantic recall vs IntentMapper).
**Honest risk level:** LOW — ArangoDB fallback is reliable.

---

## Expert Commentary

**Brandon Bailey consultation was SKIPPED** — machine at load 229, swap 100% full, scillm service unreliable under these conditions. This is a gap.

**What Brandon WOULD catch that I can't:**
- Whether the 8-entity recall result (when asking about 1 entity) would confuse the downstream QRA lookup and relationship traversal
- Whether `scope=datalake` actually returns anything useful (he knows the data)
- Whether the title parsing "What is X: ..." is universal across all 218K+ QRAs

---

## Risk Matrix

| Change | Fixes | Risk | Observable Failure | Tested? |
|--------|-------|------|--------------------|---------|
| Remove regex | F3, F5 | LOW | N/A — deletion | YES (grep confirms 0 regex) |
| --scope flag | Recall wrapper | LOW | Empty results | YES (CLI returns JSON) |
| Recall entity extraction | F2, F5 | MEDIUM | Too many entities returned | YES (1 question) |
| F36 datalake scope | F3, F5 | **HIGH** | F36 questions misclassified | **NO** |
| Short-circuit removal | F1 | LOW | N/A | YES (EC-G27 passes) |
| Gate 1 F36 check | F4 | LOW | N/A | YES (SV-IT-1 passes) |
| Intent timeout | Latency | LOW | Unnecessary fallback | YES |

---

## Remaining Risks (Honest Assessment)

### Risk 1: F36 category detection is ASPIRATIONAL (HIGH)
The `scope=datalake` recall has never been tested. If no lessons have this scope, F36 detection is completely broken. This needs to be verified against ArangoDB before trusting it.

### Risk 2: Title parsing is FRAGILE (MEDIUM)
Extracting control IDs from "What is SV-MA-3: ..." works today but assumes ALL QRA titles follow this exact format. Any title that doesn't start with "What is " will be invisible to entity extraction.

### Risk 3: Over-extraction (MEDIUM)
Asking about SV-MA-3 returns 8 entities. The evidence case pipeline processes all 8 through Gates 2-5. This adds latency and may produce confusing evidence cases with unrelated relationship paths.

### Risk 4: 50-question bank NOT RUN (HIGH)
Only 1 question tested with the current code (`_db_entity_extract` for "SV-MA-3"). The 5-question sanity from the previous session used the OLD code (with regex). The full 50-question bank has NEVER been run against any version.

---

## What Success Looks Like

| Metric | Healthy | Warning | Sick |
|--------|---------|---------|------|
| 50-question pass rate | >90% | 70-90% | <70% |
| Entity extraction accuracy | Asked entity in results | Extra entities but asked one present | Asked entity NOT in results |
| F36 detection | Correct categories found | Empty (no datalake scope) | Wrong categories |
| Per-question latency | <10s | 10-30s | >30s or timeout |
| Regex count in file | 0 | 0 | >0 |

---

## Bottom Line

**Will it work?** For pure SPARTA questions with standard control IDs — probably yes, based on the 1-question test. For F36/datalake questions — unknown, completely untested. For edge cases — unknown, the 50-question bank hasn't been run.

**What's genuinely different this time?**
1. Zero regex — verified by grep
2. All entity resolution goes through `/memory recall` + `/memory count`
3. Datalake short-circuit removed — Gates 3-5 always run
4. Classification uses Gate 1 source data, not downstream recall artifacts

**What's the same?**
1. Still uses `_sanitize_entity_id` with a character allowlist (not regex, but still string-level validation)
2. Still parses structured text from recall titles — this is string manipulation, just not regex
3. F36 detection approach changed but hasn't been validated against real data
4. 50-question bank still hasn't been run
