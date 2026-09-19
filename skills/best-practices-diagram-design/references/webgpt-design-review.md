# WebGPT diagram-design review

Source: `$ask webgpt`, sentinel `WEBGPT_DONE:20260918T145031Z:252bd15d`.

## P0 findings adopted

1. Validate the required process independently of the selected view. Reject wrong semantics, not a star-shaped layout or a connector style. Bind a source-derived requirements fragment containing required order, preconditions, and outcome targets; layout and rendering must not modify it.
2. Detect precondition bypasses by removing the required gate/outcome edge and searching from every entry. If the protected stage remains reachable, return the counterexample path.
3. Use `flowchart` with a `gated_escalation` pattern for flows with shared endings; a strict decision tree cannot contain merges.
4. Validate the actual normalized renderer scene. Measure nodes, text, edges, stroke width, transforms, and viewport after rendering. Do not accept author-written claims of collision freedom.
5. A clean straight connector may pass. An orthogonal or curved connector that crosses text must fail. Label length is advisory; measured text fit is the hard gate.

## P1 recommendations

- Add versioned renderer adapters and capability matrices for Graphviz, Mermaid, and Excalidraw.
- Add typed routing policies (`path_kind`, `corner_style`, obstacles, ports, role) rather than treating connector style as readability.
- Add display-space typography, spacing, contrast, legend, and style-token profiles.
- Bind requirements, semantic spec, measured scene, native artifact, export, renderer configuration, and screenshot by digest.
- Unsupported geometry extraction, missing fonts, or skipped mandatory checks must be `UNVERIFIED`, never PASS.

## P2 recommendations

Use mutation fixtures: correct gated escalation; star relabeled fanout; unrelated gate added to that star; direct bypass; swapped branch labels; clean straight connector; routed connector crossing text; short overflowing diamond label; five-target independent fanout; renderer/font/version changes.

## Proof boundary

These recommendations do not prove requirements were extracted correctly. They define how a diagram can prove it preserves an approved requirements fragment and how a rendered artifact can prove selected geometric properties.
