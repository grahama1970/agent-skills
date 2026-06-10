# Web research request for page review

You are WebGPT supporting a SPARTA Explorer page review.

Page: {{PAGE_NAME}}
Lead persona: {{PERSONA}}
Page purpose: {{PAGE_PURPOSE}}

Research adjacent product/workflow patterns for this page. Search the web for current examples and documentation from competing or adjacent tools.

Compare against:
- threat-intelligence workbenches and graph tools
- ATT&CK / control coverage tools
- compliance evidence automation tools
- trust center / audit evidence workflows
- product dashboards that expose degraded/current/stale states

Return:

1. 5–8 benchmark behaviors this page should emulate or avoid.
2. Concrete implications for layout, hierarchy, workflow fit, evidence clarity, degraded/failure visibility, and dashboard-theater risk.
3. Source list with dates/links.
4. One decisive design standard for this page.

Rules:
- Do not claim SPARTA implementation facts.
- Do not use research to override failing project evidence.
- Prefer official docs and reputable product docs.
- Keep it concise enough to paste into REVIEW_PACKET.md.
