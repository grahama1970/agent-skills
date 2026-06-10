# WebGPT Execution Reliability

## Assessment

`$ask webgpt` is the right front door for code and architecture review because
it preserves ask runtime artifacts, rate limits, reviewer-loop semantics, and
surf sentinel proof. Raw `$surf webgpt.submit` should remain the transport and
recovery layer.

The reliability problem is operator ergonomics, not only implementation bugs.
The current `$ask` surface is large enough that project agents can choose a
nearly-correct invocation while missing one of the browser transport invariants:

- the controlled tab must be the intended ChatGPT conversation
- `--no-activate` must not target the foreground tab
- browser reviewers need one readable bundle, not path-only manifests
- post-sentinel browser cleanup failures should not discard a completed answer

When those rules live only in `SKILL.md`, agents make avoidable mistakes and the
human ends up copy/pasting bundles by hand.

## Implemented Guardrails

`ask.webgpt_runtime.call_webgpt` now runs `surf webgpt.preflight --json` before
`surf webgpt.submit` when a tab id or URL is known. This fails before the costly
submit if the tab identity or foreground/background invariant is wrong.

The same runtime now recovers a completed WebGPT answer when `surf
webgpt.submit` exits nonzero after the raw assistant response already contains
the terminal sentinel. Recovery truncates at the sentinel so trailing page or
model contamination is not treated as clean answer text.

Focused regression tests cover:

- explicit tab id plus URL passes `--expect-url` to preflight and submit
- URL-only targeting preflights by URL
- failed preflight prevents submit
- post-sentinel submit failure recovers a clean answer

## Recommended Next Split

If failures continue, do not keep expanding the main natural-language `$ask`
surface. Add a narrow command or helper script for the common project-agent
review path:

```text
ask webgpt-review --bundle <readable-md-or-small-zip> --tab-id/--url ... --verdict PASS|NEEDS_CHANGES|BLOCKED
```

That command should own exactly one workflow:

1. validate the bundle is browser-readable
2. preflight the tab identity and background invariant
3. submit one review round
4. recover a post-sentinel answer when possible
5. write request/status/events plus clean/raw/meta artifacts
6. print the next deterministic recovery command on failure

This keeps `$ask` as the orchestration layer while giving project agents a small
pit-of-success entrypoint for WebGPT review.

