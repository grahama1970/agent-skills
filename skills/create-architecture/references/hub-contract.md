# Internal Draft Contract

The invoking agent writes these inputs after reading source. The human does
not need to operate this protocol. Paths in requests resolve relative to the
request file; CLI target/output paths resolve from the caller's directory.

```json
{
  "schema_version": 1,
  "target": "/absolute/path/to/module.py",
  "question": "Which dependencies does this module invoke?",
  "rationale": "A component view answers the dependency question.",
  "view": "structure",
  "surface": "publication",
  "sources": [{"path": "/absolute/path/to/module.py", "sha256": "REPLACE_WITH_SHA256", "start_line": 1, "end_line": 12}],
  "native_input": "components.json",
  "limitations": ["Runtime ordering is not represented."]
}
```

`sources` requires 1-80 current SHA-256 citations within the target. A single
module target may cite only that module; select its parent for broader scope.
Read relevant line ranges before selecting them. Files must be UTF-8, at most
1 MB, and outside excluded build/dependency/secret paths. Native inputs are
bounded to 2 MB. Unknown request fields and stale fingerprints fail closed.

## Native Inputs

- PHART: its supported native DAG JSON; validation precedes chart rendering.
- create-figure: JSON with `project_name` and `components`, each containing
  `name`, `type`, and explicit `dependencies`. Maximum 15 components and five
  dependencies per component, reflecting current backend limits. Unknown
  dependencies, unsafe DOT names, and normalized identity collisions fail
  rather than silently truncating the graph. Choose another surface or a
  clearly scoped view when the system exceeds these limits.
- create-svg: its native scene YAML and bundled theme. Only use a template
  whose semantics fit the source; custom theme/assets use the direct skill.
- GSN: JSON with exactly one `control` or `framework` selector. The owning
  skill retrieves actual evidence. No implicit `--dry-run` or fake evidence.

`receipt.json` binds `request.json`, the native input, artifact, and source
hashes. It records actual command argv and draft limitations; command logs
and a hash-bound `preview.html` for SVGs (via `/create-svg preview`)
are retained in successful bundles. Historical argv includes temporary paths,
so it is not a replay command. Use retained inputs to create a new request.
`status=DRAFT`, `visual_review=NOT_RUN`, and
`semantic_review=NOT_ESTABLISHED` never imply approval.

## Failure Handling

Errors go to stderr with a stable `code`; schema errors additionally expose
Pydantic `errors[].type`, `loc`, and `ctx`. Read the specific repair guidance.
Do not retry unchanged inputs. Stale sources require rereading and reauthoring;
unsupported routes require a compatible specialist, not lossy conversion.
Existing output directories are never intentionally overwritten. Failed
rendering does not publish a completed bundle; stderr identifies the failure.
