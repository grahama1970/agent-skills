# Cleanup Evidence Contract — `cleanup.evidence.v1`

Status: **implemented on both sides.**

- Producer: `$ingest-code` `scan`, Phase 0, via
  `skills/ingest-code/cleanup_evidence.py`. Enabled by default; disable with
  `--no-cleanup-evidence`. Use `--local-artifacts-only` when refreshing this
  artifact for cleanup so the scan does not store knowledge, edges, or Memory
  projections. Not emitted by `rescan`, whose `--since` filter yields a partial
  file set that cannot support a coverage claim.
- Consumer: `$cleanup` (`scan_cleanup_evidence_artifact`,
  `evaluate_candidate_dependency_evidence`).
- Reviewed-by: pending. The open questions at the end are unresolved.

## Why this exists

The aggregate marker `.ingest-code.json` holds scalar counters only
(`ingest_code.py:1901-1926`): `files_scanned`, `edges_stored`,
`code_index.symbols_stored`. `$cleanup` read those counters and printed them
beside candidates produced by a completely separate lexical scan
(`cleanup.py:628-699`), never joining the two datasets. A repository-wide
Tree-sitter ingest was therefore required before cleanup could act, while
delivering no per-file evidence about any candidate.

Three defects follow from the counter-only design, and this contract fixes each:

| Defect | Counter-only behavior | Contract requirement |
|---|---|---|
| Coverage is unproven | `files_scanned >= tracked_code_files` passes even if the wrong files were scanned (`cleanup.py:778-783`) | `files` keys are the exact repository-relative paths analyzed |
| Freshness is unreliable | `st_mtime > ingested_at` misfires after checkout, copy, rebase, or clock change (`cleanup.py:794`) | `content_sha256` per file; the consumer rehashes the working tree |
| Persistence is conflated with analysis | `_abort_if_memory_writes_incomplete` raises `SystemExit(1)` before the marker is written (`ingest_code.py:460-482`, marker at `:4152`) | the artifact is written from local analysis **before** any Memory write is attempted |

## Location and lifecycle

- Path: `<repository-root>/.cleanup-evidence.json`
- Local-only. Add to `.gitignore`. It is derived state, not a source artifact.
- Written from local Tree-sitter/AST analysis **before** Memory persistence is
  attempted. A Memory outage must leave a complete artifact on disk with
  `analysis_complete: true`; the outage is reported by the separate marker, not
  by withholding this file.
- Rewritten in full on every scan. No partial merge.

## Schema

```json
{
  "contract": "cleanup.evidence.v1",
  "generated_at": "2026-07-26T16:19:40.123456",
  "repository_path": "/home/graham/workspace/experiments/agent-skills",
  "analysis_complete": true,
  "proof_scope": {
    "languages_with_resolved_edges": ["python"],
    "languages_parsed_without_edges": ["typescript", "rust", "go"],
    "edge_kinds": ["static_import"],
    "reference_sources": ["static_import", "entrypoint", "config", "test"],
    "known_blind_spots": [
      "runtime importlib / __import__ resolution",
      "plugin discovery by naming convention",
      "shell and CI invocation of scripts by path",
      "template and data-file references"
    ]
  },
  "scan_failures": [
    {"path": "src/broken.py", "phase": "parse", "detail": "SyntaxError: line 12"}
  ],
  "files": {
    "src/pkg/module.py": {
      "content_sha256": "9f2c...",
      "git_blob_id": "a1b2c3...",
      "language": "python",
      "parse_status": "ok",
      "symbol_count": 14,
      "outbound_edges": [
        {"to_path": "src/pkg/util.py", "kind": "static_import",
         "module": "pkg.util", "names": ["helper"]}
      ],
      "inbound_references": [
        {"from_path": "src/pkg/cli.py", "kind": "static_import",
         "module": "pkg.module", "names": ["run"], "line": 7}
      ],
      "entrypoint_references": [
        {"source": "pyproject.toml", "kind": "console_script",
         "detail": "pkg-run = pkg.module:run"}
      ],
      "dynamic_reference_warnings": [
        {"from_path": "src/pkg/loader.py", "kind": "importlib",
         "detail": "importlib.import_module(name) with non-literal argument",
         "line": 22}
      ]
    }
  }
}
```

### Field requirements

| Field | Required | Meaning |
|---|---|---|
| `contract` | yes | Must equal `cleanup.evidence.v1`; consumer rejects anything else |
| `analysis_complete` | yes | `true` only when every discovered file reached a terminal `parse_status` |
| `repository_path` | yes | Absolute path of the analyzed repository root |
| `proof_scope` | yes | What the analysis can and cannot resolve. Consumers must surface this verbatim |
| `scan_failures` | yes | Every path that failed to read or parse, with phase and detail. Empty list is meaningful; a missing key is not |
| `files` | yes | Keyed by repository-relative path. The key set **is** the coverage proof |
| `files[].content_sha256` | yes | sha256 of the file bytes as analyzed. Consumer rehashes and refuses stale records |
| `files[].parse_status` | yes | `ok` \| `partial` \| `failed` \| `not_analyzed`. `not_analyzed` marks a language outside the edge-resolution scope; anything but `ok` means no reference claim can be made |
| `files[].inbound_references` | yes | Resolved references **into** this file. Empty list means "none found in scope", never "unused" |
| `files[].entrypoint_references` | yes | Console scripts, service routes, CI/shell invocations, config references. Searched across the **whole repository**, not a fixed directory list |
| `files[].entry_kinds` | yes | Why the file is an entry root on its own: `pytest_test`, `pytest_conftest`, `module_main`, `script_main`. Empty list is meaningful |
| `files[].dynamic_reference_warnings` | yes | Every dynamic-reference site the analysis could not resolve. A non-empty list blocks mutation |
| `files[].outbound_edges` | yes | Resolved dependencies out of this file |
| `files[].git_blob_id` | no | `git hash-object` value, for git-native comparison |

`inbound_references`, `entrypoint_references`, and `dynamic_reference_warnings`
must be present as lists even when empty. An absent key is treated as
`parse_failed`, not as zero references — silence must never read as safety.

## Consumer semantics (implemented)

`evaluate_candidate_dependency_evidence` returns one verdict per candidate:

| Verdict | Trigger | Mutation |
|---|---|---|
| `no_dependency_evidence` | artifact missing, invalid, or incomplete | blocked |
| `outside_proof_scope` | candidate path absent from `files` | blocked |
| `stale_evidence` | working-tree sha256 differs from `content_sha256` | blocked |
| `entry_root` | `entry_kinds` is non-empty | blocked |
| `outside_analysis_scope` | `parse_status == "not_analyzed"` (language without resolved edges) | blocked |
| `parse_failed` | any other `parse_status != "ok"` | blocked |
| `referenced` | inbound or entrypoint references exist | blocked |
| `unresolved_dynamic_references` | dynamic warnings exist | blocked |
| `no_inbound_references` | none of the above | **still blocked** pending readiness proof |

`mutation_allowed` is `False` in every branch. Static evidence narrows the
candidate set; it never authorizes the move. The `no_inbound_references` verdict
carries `readiness_required`: run the project's sanity command and
import/entrypoint smoke checks before the move, rerun both after, and restore
from quarantine on failure.

## Known gap the contract must not hide

`extract_edges` resolves edges from Python static imports only —
`if filepath.suffix != ".py": continue` (`ingest_code.py:2992-3008`). For a
JavaScript, Rust, or Go candidate, an empty `inbound_references` list carries no
information at all. The producer must therefore populate
`proof_scope.languages_parsed_without_edges` honestly, and the consumer must
refuse `no_inbound_references` for any language outside
`languages_with_resolved_edges`. Widening edge extraction beyond Python is a
prerequisite for using this artifact on non-Python candidates.

## Producer ordering (applied)

Edge resolution was hoisted out of Phase 3 into a new **Phase 0: Local
dependency analysis**, which runs immediately after file discovery and before
any Memory write:

1. Phase 0 calls `extract_edges` once, builds the artifact, and writes it.
2. Phase 3 consumes that same edge list (`edges = dependency_edges`) and only
   persists it. No edge is resolved twice.
3. `_abort_if_memory_writes_incomplete` now governs only persistence and the
   marker — never the local analysis.

The fail-closed ordering guarantee is unchanged in substance and was retargeted
in the eight tests that encoded it: they now assert `store_edges` is never
called after an earlier-phase failure, rather than `extract_edges`. Local
resolution running is not a write.

### Entrypoint detection

Two independent sources, because neither alone is sufficient:

1. **External references.** Every config, CI, manifest, and shell file in the
   repository is scanned for path-like tokens (`.toml .cfg .ini .yaml .yml .sh
   .bash` plus manifests by name; generic `.json` is excluded as data-dominated,
   and files over 2 MB are skipped). Restricting this to a fixed directory list
   made 1,078 `run.sh`/`sanity.sh` files invisible — a skill's entrypoint lives
   beside the skill.
2. **Convention entry roots** (`entry_kinds`). Nothing imports a pytest module
   or a `__main__` script, so a reference search can never see them. Detected:
   `test_*.py` / `*_test.py`, `conftest.py` under a test directory,
   `__main__.py`, and any module with an `if __name__ == "__main__"` guard.

Two precision rules keep this from over-matching:

- **Single-segment module aliases are ignored.** The bare word `cli` in a shell
  script, or `search` in a persona YAML, would otherwise mark every same-named
  module in the repository. Only dotted paths identify a module.
- **Ambiguous aliases attribute to nothing.** `src.cli` is claimed by 24 files
  in this repository; one mention identifies none of them. This mirrors
  `_resolve_unique_python_module` in the edge resolver. The count is reported as
  `proof_scope.ambiguous_module_alias_count` rather than dropped silently.

### Dynamic-reference attribution

A dynamic import with a literal prefix (`import_module(f"plugins.{name}")`)
attaches a warning to every file under that prefix. A site with no literal
prefix could target anything, so it is recorded once in
`dynamic_reference_sites` and counted in
`proof_scope.unresolved_dynamic_site_count`. The consumer attaches that count to
every `no_inbound_references` verdict as a `proof_scope_caveats` entry: one
unresolvable site bounds every no-reference claim in the repository.

The result is the four-state outcome cleanup now reports:

```
local_dependency_analysis: complete
memory_indexing: blocked
assessment: allowed
mutation: blocked until candidate-specific readiness proof
```

## Open questions for architecture review

1. Should `inbound_references` include references from untracked files, or only
   tracked ones? Untracked callers are real but not part of the committed
   contract.
2. Should the artifact be per-repository or per-scan-root, given
   `completed_scan_roots` already allows multi-root scans?
3. What is the staleness policy when only some files changed — full rescan, or
   per-file refresh keyed on `content_sha256`?
4. Does `entrypoint_references` need a pluggable extractor per ecosystem
   (`pyproject.toml`, `package.json`, `Cargo.toml`, systemd units, CI YAML)?
