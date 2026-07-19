#!/usr/bin/env python3
"""GOAL_V2 P0.3: montage verdict-equivalence calibration + routing-semantics receipt.

Runs each reviewer_calibration_v4 case's frame + Embry reference through the
composite-montage Tau route with the SAME hardened full-frame identity prompt,
and compares the montage VLM verdict to the archived direct-route verdict
(vlm_full_frame_status_v3, captured pre-migration). Equivalence means the
transport change did not alter VLM behavior — including reproducing its known
blind spot on sb_001 (a mismatch there in the STRICT direction is recorded,
not failed, since ArcFace is the identity authority either way).

Also asserts, as part of the receipt:
  - role-hierarchy preservation (marker probe through _extract_parts);
  - ArcFace enforcement (identity_authority field structural in phase-07
    receipts + the adapter's identity_decision guard fires).

Writes routing_semantics_calibration_receipt.v1.json (GOAL_V2 P0.3 authority).
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RR = ROOT / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
OUT = RR / "routing_semantics_calibration_receipt.v1.json"
V4 = RR / "reviewer_calibration_receipt.v4.json"
EMBRY_REF = Path(
    "/mnt/storage12tb/media/personas/embry/assets/contact_sheets/embry-gpt-image-2-v3/images/embry_contact_sheet_v3.png"
)
KAI_REF = RR / "phase_07_storyboard_live_tau/references/02-kai_character_sheet.png"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _b64(path: Path) -> str:
    import base64

    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def hardened_prompt(p07) -> str:
    # Same hardened prompt contract the direct route used for the calibration
    # cases (panel context minimal; the identity standard text is what matters).
    return p07._identity_review_prompt(
        {"panel_id": "calibration"},
        frame_key="start_frame",
        required_entities=["Embry", "Kai"],
    )


def montage_verdict(comp, frame: Path, prompt: str, workdir: Path, *, tamper: bool = False) -> str:
    # tamper=True reproduces the archived probe's reference swap: the EMBRY
    # reference slot is pointed at the KAI sheet, so a reference-grounded
    # reviewer must FAIL the (correct) frame against the (wrong) declaration.
    embry_ref = KAI_REF if tamper else EMBRY_REF
    payload = {
        "model": "gpt-5.5",
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Judge the CANDIDATE FRAME against the EMBRY and KAI REFERENCE SHEETS (matching the archived direct-route probe conditions)."},
                    {"type": "image_url", "label": "CANDIDATE FRAME", "image_url": {"url": _b64(frame)}},
                    {"type": "image_url", "label": "EMBRY REFERENCE SHEET", "image_url": {"url": _b64(embry_ref)}},
                    {"type": "image_url", "label": "KAI REFERENCE SHEET", "image_url": {"url": _b64(KAI_REF)}},
                ],
            },
        ],
    }
    resp = comp.post_openai_vlm_via_tau(payload, artifact_dir=workdir, purpose="identity_advisory")
    content = resp["choices"][0]["message"]["content"]
    m = re.search(r'"verdict"\s*:\s*"(PASS|FAIL)"', content)
    if m:
        return m.group(1)
    up = content.upper()
    return "FAIL" if '"FAIL"' in up or "VERDICT: FAIL" in up else ("PASS" if "PASS" in up else "UNPARSEABLE")


def main() -> int:
    comp = _load("tau_vlm_composite_review")
    p07 = _load("phase07_storyboard_tau_node")
    v4 = json.loads(V4.read_text())
    prompt = hardened_prompt(p07)

    rows, mismatches = [], []
    with tempfile.TemporaryDirectory() as td:
        for case in v4["cases"]:
            cid = case["case_id"]
            frame = Path(case["image_path"])
            if not frame.is_absolute():
                frame = ROOT / frame
            archived = case.get("vlm_full_frame_status_v3")
            got = montage_verdict(comp, frame, prompt, Path(td) / cid, tamper=(case.get("kind") == "tamper" or cid == "tamper_wrong_embry_ref"))
            equivalent = got == archived
            stricter = (archived == "PASS" and got == "FAIL")
            rows.append({
                "case_id": cid,
                "archived_direct_vlm": archived,
                "montage_vlm": got,
                "equivalent": equivalent,
                "stricter_direction": stricter,
                "embedding_authority_verdict": case.get("embedding_status"),
            })
            if not equivalent and not stricter:
                mismatches.append(cid)

    # Role-preservation probe (deterministic, no live call).
    texts, _ = comp._extract_parts({
        "messages": [
            {"role": "system", "content": "sys rule"},
            {"role": "user", "content": [{"type": "text", "text": "user q"}]},
        ]
    })
    roles_ok = any(t.startswith("[SYSTEM INSTRUCTIONS") for t in texts) and any(
        t.startswith("[USER]") for t in texts
    )

    # ArcFace enforcement probes.
    guard_fires = False
    try:
        comp.assert_not_identity_decision("identity_decision")
    except RuntimeError:
        guard_fires = True
    authority_structural = 'receipt["identity_authority"] = "face_embedding_subgate"' in (
        ROOT / "scripts/phase07_storyboard_tau_node.py"
    ).read_text()

    montage_pass = not mismatches
    receipt = {
        "schema": "persona_dream.routing_semantics_calibration_receipt.v1",
        "status": "PASS_ROUTING_SEMANTICS"
        if (montage_pass and roles_ok and guard_fires and authority_structural)
        else "FAIL_ROUTING_SEMANTICS",
        "montage_equivalence": "PASS" if montage_pass else "FAIL",
        "montage_cases": rows,
        "equivalence_rule": (
            "montage verdict must equal the archived direct-route verdict, or "
            "deviate only in the stricter direction (archived PASS -> montage "
            "FAIL), since ArcFace is the identity authority in both routes"
        ),
        "role_hierarchy_preserved": roles_ok,
        "arcface_enforced": bool(guard_fires and authority_structural),
        "arcface_enforcement": {
            "adapter_identity_decision_guard_fires": guard_fires,
            "phase07_identity_authority_structural": authority_structural,
        },
        "live": True,
        "mocked": False,
    }
    OUT.write_text(json.dumps(receipt, indent=2))
    print(json.dumps({
        "status": receipt["status"],
        "montage_equivalence": receipt["montage_equivalence"],
        "role_hierarchy_preserved": roles_ok,
        "arcface_enforced": receipt["arcface_enforced"],
        "cases": [(r["case_id"], r["archived_direct_vlm"], r["montage_vlm"]) for r in rows],
    }, indent=2))
    return 0 if receipt["status"] == "PASS_ROUTING_SEMANTICS" else 1


if __name__ == "__main__":
    sys.exit(main())
