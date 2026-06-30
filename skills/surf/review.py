"""Module support for the surf skill."""
import os
import base64
import json
import httpx

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

image_path = "${HOME}/workspace/experiments/sparta/.reviews/sparta-chat/cursor-gemini-loop/compare-pane.png"
base64_image = encode_image(image_path)

prompt = """You are a strict design reviewer for the SPARTA Chat pane.

Evaluate EVERY punch-list item (A1–F1) against the attached screenshot only.
Respect scope.exclude and scope.context below.
Do NOT fail verdict-gated behavior (no Inconclusive chip when no verdict).
Do NOT confuse the crosswalk FIGURE boxes with footer status badges.

Scope:
    "target": "chat pane only — data-qid=chat:well:root",
    "exclude": ["center Threat Matrix pane", "left nav sidebar", "global status bar"],
    "context": {
      "crosswalk_figure": "Vendor attestation / SBOM freshness / Source hash / Reviewer approval boxes are an embedded FIGURE diagram, not footer status badges",
      "verdict_gating": "Inconclusive status chip appears only when an evidence-case verdict exists; turns without verdict show provenance only"
    }

Punch list items:
A1: Footer row uses flex space-between; meta left, actions right — not a single log-line string
A2: Left: sample-derived + Inconclusive ghost tag when verdict present. Styles: provenance: fontSize 10px, color #9aa0a6. inconclusive_tag: color #ffab00, background rgba(255,171,0,0.05), border 1px solid rgba(255,171,0,0.3), fontSize 10px, borderRadius 4px
A3: Right: Trace (no brackets, #8ab4f8, Route icon) + timestamp (#5f6368, 11px)
A4: Footer top border: 1px solid rgba(255,255,255,0.05)
B1: Floating pill composer. Styles: background #1e1f20, border 1px solid #3c4043, borderRadius 28px, padding 12px 20px
B2: + and send icons vertically centered
B3: Focus border #8ab4f8
C1: User Well: bg rgba(255,255,255,0.03), radius 12px, padding 16px, line-height 1.5
D1: Artifact cards: border 1px rgba(255,255,255,0.1), radius 12px, subtle shadow
D2: Drilldown active header: #9aa0a6, 11px (not loud amber)
E1: Inter for chrome; JetBrains Mono only for hashes/IDs
F1: No bracket UI literals ([Trace], [New project], etc.)

Return ONLY valid JSON matching this schema:
{
  "verdict": "satisfied" | "needs_changes" | "insufficient_evidence",
  "items": [{"id": "string", "status": "pass" | "fail" | "n/a", "note": "string"}],
  "blocking_changes": ["string"],
  "missing_evidence": ["string"]
}"""

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer sk-dev-proxy-123",
    "X-Caller-Skill": "review-design"
}

payload = {
    "model": "claude-sonnet",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
        }
    ],
    "temperature": 0.0
}

response = httpx.post("http://localhost:4001/v1/chat/completions", headers=headers, json=payload)
print(json.dumps(response.json(), indent=2))
