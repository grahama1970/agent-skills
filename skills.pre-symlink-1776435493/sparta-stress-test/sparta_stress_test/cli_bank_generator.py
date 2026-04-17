"""Question bank generators for SPARTA stress testing.

Contains generate_full_bank() (legacy template-fill), generate_mined_bank()
(data-mining pipeline), and helpers (_load_ground_truth, _default_sv_controls)
extracted from cli.py to keep each module under 800 lines.
"""

import json
import sys
from pathlib import Path

from loguru import logger


def generate_mined_bank(total: int, question_miner, question_quality) -> list[dict]:
    """Generate question bank via data-mining pipeline.

    1. Mine from all 4 ArangoDB sources
    2. Quality gate each question (7 criteria)
    3. Taxonomy coverage balance
    4. Deduplicate final set
    5. Shuffle
    """
    import random

    # Step 1: Mine raw questions (request 2x to account for quality gate rejections)
    raw = question_miner.mine_all(total=int(total * 2))

    # Step 2: Quality gate
    accepted, rejected = question_quality.quality_gate(raw)
    logger.info(f"Quality gate: {len(accepted)} accepted, {len(rejected)} rejected")

    # Step 3: Taxonomy coverage balance
    accepted = question_quality.balance_taxonomy(accepted)

    # Step 4: Trim to target count
    if len(accepted) > total:
        random.shuffle(accepted)
        accepted = accepted[:total]

    # Step 5: Deduplicate IDs (ensure uniqueness)
    seen_ids = set()
    final = []
    for q in accepted:
        if q["id"] not in seen_ids:
            seen_ids.add(q["id"])
            final.append(q)

    random.shuffle(final)
    return final


def _load_ground_truth() -> dict:
    """Try to load SPARTA ground truth from spreadsheet."""
    try:
        _project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        sparta_spreadsheet = _project_root / "sparta" / "data" / "source" / "SPARTA-Data.xlsx"
        if not sparta_spreadsheet.exists():
            return {"controls": {}, "techniques": {}, "countermeasures": {}}

        # Reuse the loader from monitor_sparta if available
        # monitor_sparta.py lives in the memory project, not pi-mono
        _memory_validation = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "memory" / "scripts" / "validation")
        if not Path(_memory_validation).exists():
            # Fallback: try pi-mono path
            _memory_validation = str(Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "validation")
        sys.path.insert(0, _memory_validation)
        from monitor_sparta import _load_sparta_ground_truth
        return _load_sparta_ground_truth()
    except Exception:
        return {"controls": {}, "techniques": {}, "countermeasures": {}}


def _default_sv_controls() -> list[str]:
    """Fallback list of known SV-* control IDs."""
    return [
        "SV-SP-1", "SV-SP-2", "SV-SP-3", "SV-SP-4", "SV-SP-5",
        "SV-SP-6", "SV-SP-7", "SV-SP-8", "SV-SP-9", "SV-SP-10", "SV-SP-11",
        "SV-AC-1", "SV-AC-2", "SV-AC-3", "SV-AC-4", "SV-AC-5",
        "SV-AC-6", "SV-AC-7",
        "SV-MA-1", "SV-MA-2", "SV-MA-3", "SV-MA-4",
        "SV-IT-1", "SV-IT-2", "SV-IT-3", "SV-IT-4",
        "SV-CF-1", "SV-CF-2", "SV-CF-3",
        "SV-AV-1", "SV-AV-2", "SV-AV-3", "SV-AV-4", "SV-AV-5",
        "SV-AV-6", "SV-AV-7",
        "SV-DCO-1", "SV-DCO-2",
    ]


def generate_full_bank(total: int = 1000) -> list[dict]:
    """Generate the full question bank.

    Distribution:
        Simple (30%):    Single-control, correct IDs, direct lookup
        Medium (25%):    Cross-control, cross-framework, multi-CM
        Complex (20%):   Multi-hop, F-36 LEO specific, synthesis
        Ambiguous (15%): Vague, overly broad, no specifics
        Flawed (10%):    Wrong IDs, ATT&CK-not-SPARTA, invalid format
    """
    import random

    simple_count = int(total * 0.30)
    medium_count = int(total * 0.25)
    complex_count = int(total * 0.20)
    ambiguous_count = int(total * 0.15)
    flawed_count = total - simple_count - medium_count - complex_count - ambiguous_count

    # Load ground truth if available
    gt = _load_ground_truth()
    controls = gt.get("controls", {})
    ctrl_ids = list(controls.keys()) if controls else _default_sv_controls()

    bank = []
    idx = 0

    # --- Simple questions ---
    simple_templates_margaret = [
        "What are the countermeasures for {ctrl}?",
        "Describe the threat profile of {ctrl} ({name}).",
        "Which techniques target {ctrl}?",
        "How is {ctrl} mitigated in the SPARTA framework?",
        "What is the purpose of {ctrl}?",
        "List the NIST cross-references for {ctrl}.",
        "What detection methods apply to {ctrl}?",
    ]
    simple_templates_jennifer = [
        "What is the compliance posture of {ctrl}?",
        "Which RMF controls map to {ctrl}?",
        "What CAT findings relate to {ctrl}?",
        "How does {ctrl} affect the authorization boundary?",
        "What evidence is required for {ctrl} in an SSP?",
        "What is the residual risk for {ctrl}?",
    ]

    for i in range(simple_count):
        ctrl_id = ctrl_ids[i % len(ctrl_ids)]
        ctrl = controls.get(ctrl_id, {"name": ctrl_id})
        if i % 2 == 0:
            tmpl = simple_templates_margaret[i % len(simple_templates_margaret)]
            persona = "Margaret Chen"
        else:
            tmpl = simple_templates_jennifer[i % len(simple_templates_jennifer)]
            persona = "Jennifer Cheung"

        bank.append({
            "id": f"simple-{idx:04d}",
            "difficulty": "simple",
            "persona": persona,
            "question": tmpl.format(ctrl=ctrl_id, name=ctrl.get("name", "")),
            "expected_action": "QUERY",
            "target_control": ctrl_id,
            "expected_techniques": ctrl.get("techniques", [])[:3],
            "expected_countermeasures": ctrl.get("countermeasures", [])[:3],
            "grading_notes": "Direct single-control lookup",
        })
        idx += 1

    # --- Medium questions ---
    medium_templates = [
        "Compare the threat models of {ctrl1} and {ctrl2} for satellite communications.",
        "How do the countermeasures for {ctrl1} overlap with {ctrl2}?",
        "What NIST 800-53 controls apply to both {ctrl1} and {ctrl2}?",
        "Which CWE weaknesses are relevant to both {ctrl1} and {ctrl2}?",
        "How do ATT&CK techniques T1071 and T1059 map to {ctrl1}?",
    ]

    for i in range(medium_count):
        c1_idx = i % len(ctrl_ids)
        c2_idx = (i + 1) % len(ctrl_ids)
        ctrl1 = ctrl_ids[c1_idx]
        ctrl2 = ctrl_ids[c2_idx]
        tmpl = medium_templates[i % len(medium_templates)]
        persona = "Margaret Chen" if i % 2 == 0 else "Jennifer Cheung"

        ctrl_data = controls.get(ctrl1, {})
        bank.append({
            "id": f"medium-{idx:04d}",
            "difficulty": "medium",
            "persona": persona,
            "question": tmpl.format(ctrl1=ctrl1, ctrl2=ctrl2),
            "expected_action": "QUERY",
            "target_control": ctrl1,
            "expected_techniques": ctrl_data.get("techniques", [])[:3],
            "expected_countermeasures": ctrl_data.get("countermeasures", [])[:3],
            "grading_notes": "Cross-control comparison",
        })
        idx += 1

    # --- Complex questions ---
    complex_templates = [
        "For the F-36 LEO mission, trace the attack chain from {ctrl1} through {ctrl2} and assess the aggregate risk to the avionics bus.",
        "How would an adversary combine {ctrl1} exploitation with {ctrl2} to achieve persistent access in the F-36 LEO segment?",
        "What multi-layered defense architecture addresses both {ctrl1} and {ctrl2} for the F-36 re-entry phase?",
        "Analyze the cross-domain implications of {ctrl1} when the F-36 transitions from atmospheric to orbital operations.",
    ]

    for i in range(complex_count):
        c1_idx = i % len(ctrl_ids)
        c2_idx = (i + 3) % len(ctrl_ids)
        ctrl1 = ctrl_ids[c1_idx]
        ctrl2 = ctrl_ids[c2_idx]
        tmpl = complex_templates[i % len(complex_templates)]
        persona = "Margaret Chen" if i % 2 == 0 else "Jennifer Cheung"

        ctrl_data = controls.get(ctrl1, {})
        bank.append({
            "id": f"complex-{idx:04d}",
            "difficulty": "complex",
            "persona": persona,
            "question": tmpl.format(ctrl1=ctrl1, ctrl2=ctrl2),
            "expected_action": "QUERY",
            "target_control": ctrl1,
            "expected_techniques": ctrl_data.get("techniques", [])[:5],
            "expected_countermeasures": ctrl_data.get("countermeasures", [])[:5],
            "grading_notes": "Multi-hop synthesis, F-36 specific",
        })
        idx += 1

    # --- Ambiguous questions ---
    ambiguous_questions = [
        "What about access control for the F-36?",
        "Tell me about security.",
        "How does protection work?",
        "Threats?",
        "What can you tell me about satellites?",
        "Is the F-36 secure?",
        "How do we defend against attacks?",
        "What about compliance?",
        "Tell me about space.",
        "How does the framework work?",
        "What are the risks?",
        "Can you explain the controls?",
        "What should I be worried about?",
        "How do we protect the mission?",
        "Tell me about vulnerabilities.",
        "What about the ground segment?",
        "Security posture?",
        "How resilient is it?",
        "What about authentication?",
        "Defense in depth?",
    ]

    for i in range(ambiguous_count):
        q_text = ambiguous_questions[i % len(ambiguous_questions)]
        persona = "Margaret Chen" if i % 2 == 0 else "Jennifer Cheung"

        bank.append({
            "id": f"ambiguous-{idx:04d}",
            "difficulty": "ambiguous",
            "persona": persona,
            "question": q_text,
            "expected_action": "CLARIFY",
            "target_control": None,
            "expected_techniques": [],
            "expected_countermeasures": [],
            "grading_notes": "Too vague -- should trigger disambiguation",
        })
        idx += 1

    # --- Flawed questions ---
    fake_controls = [
        "SV-SP-99", "SV-ZZ-1", "SV-99", "SV-AC-99", "SV-IT-99",
        "SV-MA-99", "SV-XX-01", "CTRL-001", "NIST-999",
    ]
    flawed_templates = [
        "What countermeasures does {fake} prescribe for the F-36 LEO avionics bay?",
        "Describe the threat profile of {fake}.",
        "Which techniques are mapped to {fake}?",
        "What is the compliance status of {fake}?",
        "How does {fake} relate to GPS spoofing?",
    ]

    for i in range(flawed_count):
        fake = fake_controls[i % len(fake_controls)]
        tmpl = flawed_templates[i % len(flawed_templates)]
        persona = "Margaret Chen" if i % 2 == 0 else "Jennifer Cheung"

        bank.append({
            "id": f"flawed-{idx:04d}",
            "difficulty": "flawed",
            "persona": persona,
            "question": tmpl.format(fake=fake),
            "expected_action": "NO_MATCH",
            "target_control": fake,
            "expected_techniques": [],
            "expected_countermeasures": [],
            "grading_notes": f"Non-existent control {fake} -- should trigger error detection",
        })
        idx += 1

    random.shuffle(bank)
    return bank
