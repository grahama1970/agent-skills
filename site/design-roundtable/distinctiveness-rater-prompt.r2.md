# grahama.co Blind Distinctiveness Rater Prompt r2

You are one independent rater. Do not collaborate with other raters. Inspect the attached blinded contact-sheet image.

## Target Brief

The unlabeled screens come from a personal site for an engineer who builds agent systems that prove what they did. The selected visual world is **Proof Workshop**: claims become permissible only when traced through evidence to bounded judgments.

Expected non-color invariants include:

- human narrative roles separated from machine evidence roles;
- local evidence/provenance margins;
- visible proof boundaries, unresolved gaps, or claim-to-judgment structure.

## Same-Category Decoy Briefs

1. **Generic AI Systems Portfolio**: a polished portfolio for an AI consultant showing capabilities, projects, testimonials, contact, card grids, metrics, and smooth dark startup styling.
2. **Compliance Automation Vendor**: a B2B tool for audit readiness and evidence collection, organized around dashboards, controls, reports, status badges, and enterprise proof points.
3. **Cybersecurity Research Portfolio**: a personal security research site, organized around exploits, writeups, CVEs, tool releases, and hacker/cyber motifs.

## Blinded Screens

The attached contact sheet has logo and brand name removed. Some project nouns remain because competitor-swap is a separate gate.

## Required Output

Return exactly this structure:

```text
RATER_ID: <your handler/model name if known>
LOGO_OFF_MATCH: <Proof Workshop | Generic AI Systems Portfolio | Compliance Automation Vendor | Cybersecurity Research Portfolio>
LOGO_OFF_CONFIDENCE: <0-100>
TEN_SECOND_CLASSIFICATION: <one short phrase>
GENERIC_AI_TEMPLATE_PRIMARY: <yes | no>
EVIDENCE_FIRST_SIGNALS: <comma-separated concrete visible signals>
NON_COLOR_INVARIANTS: <at least three, or INSUFFICIENT>
COMPETITOR_SWAP_TENSION: <yes | no>
CROSS_SCREEN_FAMILY: <yes | no>
REFERENCE_OR_CRAFT_LEAKAGE_RISK: <none | low | medium | high, with reason>
VERDICT: <PASS | FAIL | INSUFFICIENT_EVIDENCE>
```

## Scoring Rubric

PASS only if you can match the screens to Proof Workshop without relying on logo, name, or color alone, identify evidence/accountability/claim-to-judgment as the distinguishing idea, and name at least three non-color invariants across screens.

Mark FAIL if this reads primarily as a generic AI portfolio/template.

Mark INSUFFICIENT_EVIDENCE if the image is not visible or too small to inspect.
