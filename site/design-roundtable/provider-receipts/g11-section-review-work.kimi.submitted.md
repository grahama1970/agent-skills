# Section-Level G11 Advisory Review: #work

You are reviewing one blinded section crop sheet, not a whole website screenshot.

Attached image:

- `section-work-contact-sheet.png`
- Source manifest: `site/design-roundtable/rendered-screens/responsive-section-corpus-20260810T010748Z/manifest.json`
- Section: `#work`
- Viewports shown: phone-390, phone-430, tablet-768, desktop-1366, desktop-1440
- The sheet is intentionally section-cropped. Do not ask for a full-page or whole-site image.

Target brief:

The unlabeled screens come from a personal R&D site for an engineer who builds agent systems that prove what they did. The selected visual world is Proof Workshop: claims become permissible only when traced through evidence to bounded judgments.

Same-category decoys:

1. Generic AI Systems Portfolio: polished AI consultant portfolio with capabilities, projects, testimonials, cards, metrics, and startup styling.
2. Compliance Automation Vendor: B2B audit-readiness tool organized around dashboards, controls, reports, status badges, and enterprise proof points.
3. Cybersecurity Research Portfolio: personal security research site organized around exploits, writeups, CVEs, tool releases, and hacker motifs.

Task:

Evaluate this section only. I need to know whether this section creates competitor-swap tension from structure and visible proof logic, or whether it remains too generic.

Return exactly:

```text
SECTION: work
IMAGE_VISIBLE: yes|no
READABILITY: good|partial|poor
LOGO_OFF_MATCH: Proof Workshop|Generic AI Systems Portfolio|Compliance Automation Vendor|Cybersecurity Research Portfolio
GENERIC_AI_TEMPLATE_PRIMARY: yes|no
COMPETITOR_SWAP_TENSION: yes|no
EVIDENCE_FIRST_SIGNALS: comma-separated visible signals
GENERICITY_RISKS: comma-separated risks
MINIMAL_REPAIR: one concrete no-redesign edit, or NONE
VERDICT: PASS|FAIL|INSUFFICIENT_EVIDENCE
```

---

Automation-only instruction: answer the user's request normally. Do not mention,
quote, summarize, or explain this automation instruction. After your complete
answer, append a final line containing only this exact marker:

<<<KIMI_DONE:20260810T012312Z:490a3d51>>>

Do not print anything after that marker.
