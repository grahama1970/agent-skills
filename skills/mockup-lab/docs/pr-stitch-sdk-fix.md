# PR: Stitch SDK Fixes (3 bugs)

**Upstream repo**: [google-labs-code/stitch-sdk](https://github.com/google-labs-code/stitch-sdk)
**Fork**: [grahama1970/stitch-sdk](https://github.com/grahama1970/stitch-sdk)
**Branch**: `fix/resilient-response-parsing`
**Local path**: `${HOME}/workspace/experiments/stitch-sdk`
**SDK version**: 0.0.3
**Status**: Testing locally before upstream PR

---

## Bug 1: Response parsing crash in generate/edit/variants

**Symptom**: `Cannot read properties of undefined (reading 'screens')`

Three SDK methods crash on API responses that don't match the hardcoded projection path:

| Method | Expected path | Actual API response |
|--------|--------------|---------------------|
| `project.generate()` | `raw.outputComponents[0].design.screens[0]` | `designSystem` instead of `design`, or screens at different nesting |
| `screen.edit()` | same | same |
| `screen.variants()` | `flatMap → design.screens` | same |

**Root cause**: `domain-map.json` defines a static projection emitted as a raw property chain
with no optional chaining or fallback.

**Fix**: New file `packages/sdk/generated/src/response-utils.ts` with:

- **`extractScreenData(raw)`** — tries 6 paths in order:
  1. Canonical: `outputComponents[0].design.screens[0]`
  2. Direct screens: `outputComponents[0].screens[0]`
  3. Component as screen: `outputComponents[0]` itself
  4. Top-level: `raw.screens[0]`
  5. Flat: `raw` itself (if screen-like)
  6. Search: iterate all `outputComponents` checking `design.screens` and `designSystem.screens`

- **`extractScreenDataArray(raw)`** — same for multi-screen responses (variants)
- **`isScreenLike(obj)`** — duck-type check: has `id`, `name` with `/screens/`, `htmlCode`, or `screenshot`

## Bug 2: callTool doesn't retry on transient network errors

**Upstream issue**: [#114](https://github.com/google-labs-code/stitch-sdk/issues/114)
**Upstream PR**: [#117](https://github.com/google-labs-code/stitch-sdk/pull/117) by icebear0828

**Symptom**: `TypeError: fetch failed` / `SocketError: other side closed` during concurrent requests

**Fix** (cherry-picked from PR #117):
- `RETRYABLE_TOOLS` allowlist: `list_projects`, `get_project`, `list_screens`, `get_screen`
- `isNetworkError()` detects: fetch failed, ECONNREFUSED, ECONNRESET, ETIMEDOUT, socket hang up, other side closed
- Reconnects and retries once for idempotent reads before throwing
- Write operations (generate, edit, create) are NOT retried — not idempotent

## Bug 3: create_project → screens race condition

**Symptom**: `project.screens()` returns empty array immediately after `createProject()` +
`generate()` because the API hasn't settled yet.

**Fix**:
- `createProject()` marks `project._isNew = true`
- `screens()` retries 3x with 2s settle delay when empty on fresh projects
- `getScreen()` retries on `NOT_FOUND` for fresh projects (3x, 2s apart)
- Once screens are found, no further delays on subsequent calls

## Files Changed

```
 packages/sdk/src/client.ts                    |  53 ++++++++-  (Bug 2: network retry)
 packages/sdk/generated/src/response-utils.ts  | 104 +++++++++++++++++ (Bug 1: resilient parsing)
 packages/sdk/generated/src/project.ts         |  45 +++++--- (Bug 1 + Bug 3)
 packages/sdk/generated/src/screen.ts          |  12 ++-  (Bug 1)
 packages/sdk/generated/src/stitch.ts          |   3 +-   (Bug 3: _isNew flag)
```

## How pi-mono Uses the Fork

```bash
# pi-mono's package.json points to the local fork (npm install from path)
npm install ${HOME}/workspace/experiments/stitch-sdk/packages/sdk
```

Any code that does `import { stitch } from "@google/stitch-sdk"` gets the patched version.
No changes needed in consuming code.

`mockup-lab/stitch_cli.mjs` also has belt-and-suspenders bypasses (callTool + getScreen retry)
that work independently of the SDK fixes.

## Testing

- [x] TypeScript compiles clean (`npx tsc` — zero errors)
- [x] `mockup-lab` sanity: 11/11 pass
- [x] `test-lab` blind adversarial: 9/9 pass
- [x] `skills-ci`: zero violations for mockup-lab
- [ ] Live API: `createProject()` → `generate()` → `screens()` on fresh project
- [ ] Live API: `screen.edit()` response parsing
- [ ] Live API: `screen.variants()` response parsing
- [ ] Live API: concurrent `edit()` calls trigger network retry

## When to Submit Upstream

After all live API tests pass locally. Consider splitting into 2-3 PRs:
1. Response parsing resilience (Bug 1) — independent, no overlap with #117
2. Network retry (Bug 2) — coordinate with or defer to PR #117
3. Settle delay (Bug 3) — independent, could be a separate PR or bundled with Bug 1

Also file an issue describing the API/SDK response shape mismatch — the proper fix
may be in `domain-map.json` or the code generator, not just the generated output.

## Related mockup-lab Changes (same session)

1. `explore` views parameterized via `--views <file.json>` (was hardcoded to binary-explorer)
2. `read_before_use: stitch_cli.mjs` added to frontmatter
3. `spec-template.md` created for agent use
4. `converge` documented as one-shot (loop is agent-driven)
5. `getScreen()` retry helper for screen visibility race condition (3x, 2s apart)
6. `generateScreen()` bypass using `callTool` directly

## Upstream Feature Request: Collaboration API

**Filed**: [#129](https://github.com/google-labs-code/stitch-sdk/issues/129)

**Problem**: Stitch's web UI has comments and chat on projects/screens, but the MCP server
exposes zero tools for reading or writing them. The 8 available tools are:

```
create_project, get_project, list_projects, list_screens, get_screen,
generate_screen_from_text, edit_screens, generate_variants
```

No `list_comments`, `add_comment`, `get_chat_history`, `get_feedback`.

**Impact**: Agents can generate designs but can't read human feedback left in Stitch's
collaboration UI. The feedback loop is severed — agents must use external channels
(/interview, local files) instead of the native Stitch review workflow.

**Requested tools**:

| Tool | Purpose |
|------|---------|
| `list_comments` | Read comments on a project or screen |
| `add_comment` | Agent posts a comment (e.g., review findings, questions) |
| `get_chat_history` | Read the chat/collaboration thread for a project |
| `resolve_comment` | Mark a comment as addressed after iteration |

This would close the loop: human reviews in Stitch web UI → leaves comments → agent reads
comments via API → iterates → posts response. No external tools needed.

**Workaround**: Agent pulls screenshots locally, collects feedback via `/interview` skill,
feedback lives in our system not Stitch's.
