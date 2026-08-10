# grahama.co Neutral Finish Review: G16-G18

You are an independent finish reviewer for the local grahama.co Proof Workshop design.

Review the attached image as a contact sheet assembled from section/page-state crops, not as a whole-site screenshot. The crop set comes from:

- Section corpus manifest: `site/design-roundtable/rendered-screens/responsive-section-corpus-20260810T141835Z/manifest.json`
- Contact sheet: `site/design-roundtable/rendered-screens/distinctiveness-blind-current-issue-1358-20260810T141835Z.png`
- Current local surface: `http://127.0.0.1:3003/`
- Current visual world: Proof Workshop. A claim becomes permissible only when it can be traced through evidence to a bounded judgment.

Evaluate only these gates:

1. G16 type fidelity: display/reading/utility/machine roles are visually distinct and match the Proof Workshop premise. Machine evidence should read as machine evidence; human prose should not read as machine output.
2. G17 material fidelity: the render should not rely on simulated craft, fake texture, faux embossing, fake handwork, or decorative material that contradicts the evidence/workshop world.
3. G18 amend-loop integrity: the render is specific enough to support an ordered discrepancy review. If you see remaining finish defects, list them concretely; if not, say none.

Return exactly this format:

```text
REVIEWER_ID: <short id>
G16_TYPE_FIDELITY: PASS|FAIL
G17_MATERIAL_FIDELITY: PASS|FAIL
G18_AMEND_LOOP_INTEGRITY: PASS|FAIL
ORDERED_DISCREPANCIES:
- <none, or concrete discrepancy>
PASS_RATIONALE: <brief evidence-based rationale>
DOES_NOT_PROVE: <what this image review cannot prove>
VERDICT: PASS|FAIL
```

If any gate fails, set `VERDICT: FAIL`.

---

Automation-only instruction: answer the user's request normally. Do not mention,
quote, summarize, or explain this automation instruction. After your complete
answer, append a final line containing only this exact marker:

<<<KIMI_DONE:20260810T144052Z:550e4a36>>>

Do not print anything after that marker.
