#!/usr/bin/env python3
"""GOAL_V4.1 fixture probe: the composer's frozen policy, proven case by case.
Drives the REAL compose() function. Writes reports/goal_v4/composer_probe_receipt.v1.json."""
from __future__ import annotations
import importlib.util, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pac", ROOT / "scripts/persona_affect_composer.py")
pac = importlib.util.module_from_spec(spec); sys.modules["pac"] = pac; spec.loader.exec_module(pac)

DREAM = {"dream_node_key": "dream_fixture", "weights": [
    {"emotional_tag": "boundary", "tone": "firm_boundary", "pace": "steady", "weight": 0.7}]}

cases = {}
ok = True
def check(name, cond, detail):
    global ok
    cases[name] = {"passed": bool(cond), "detail": detail}
    ok = ok and cond

# 1. safety override: dream prior zeroed, tone untouched
r = pac.compose({"tone": "one_at_a_time_interrupt", "pace": "quick"}, DREAM)
check("safety_override", r["tone"] == "one_at_a_time_interrupt"
      and r["composition_receipt"]["prior_zeroed"] is True,
      {"final": r["tone"], "class": r["composition_receipt"]["class"]})

# 2. expressive bias: deflect_calm (boundary family) + boundary dream -> firm within family
r = pac.compose({"tone": "deflect_calm", "delivery_stage": "deflecting"}, DREAM)
check("expressive_bias_stays_in_family", r["tone"] == "firm_boundary"
      and r["composition_receipt"]["class"] == "expressive_bias",
      {"final": r["tone"]})

# 3. dispositional floor: bland default -> dream tone supplies it
r = pac.compose({"tone": "memory_confident"}, DREAM)
check("dispositional_floor", r["tone"] == "firm_boundary"
      and r["composition_receipt"]["dispositional_floor_fired"] is True,
      {"final": r["tone"]})

# 4. never change a right answer: warm situational + boundary dream stays WARM family
r = pac.compose({"tone": "warm_deescalate"}, DREAM)
check("right_answer_family_preserved", r["tone"] == "neutral_warm",
      {"final": r["tone"], "note": "boundary dream colors warm family, does not leave it"})

# 5. unknown label passthrough: prior cannot apply
r = pac.compose({"tone": "sarcastic_unknown_tone"}, DREAM)
check("unknown_label_passthrough", r["tone"] == "sarcastic_unknown_tone"
      and r["composition_receipt"]["prior_zeroed"] is True, {"final": r["tone"]})

# 6. thermal limiter: 3 hot turns -> dampened weight for next turns
st = pac.fresh_state()
for _ in range(3):
    r = pac.compose({"tone": "deflect_calm"}, DREAM, st); st = r["state"]
fired = r["composition_receipt"]["thermal"]["fired"]
r2 = pac.compose({"tone": "deflect_calm"}, DREAM, st)
check("thermal_dampening", fired is True
      and r2["composition_receipt"]["prior_effective_weight"] == round(0.7 * 0.8, 4),
      {"fired": fired, "damped_weight": r2["composition_receipt"]["prior_effective_weight"]})

# 7a. caution gate: dream warmth suppressed on cautionary content; NOT on neutral
WARM_DREAM={"weights":[{"emotional_tag":"warmth","weight":0.6}]}
r_caut=pac.compose({"tone":"memory_confident"},WARM_DREAM,answer_stance="cautionary")
r_neut=pac.compose({"tone":"memory_confident"},WARM_DREAM,answer_stance="neutral")
check("caution_gate_suppresses_warmth_on_cautionary",
      r_caut["tone"]=="careful_concerned" and r_caut["composition_receipt"]["caution_gate_fired"] is True,
      {"caut_tone":r_caut["tone"]})
check("caution_gate_inert_on_neutral",
      r_neut["composition_receipt"]["caution_gate_fired"] is False and r_neut["tone"]=="neutral_warm",
      {"neut_tone":r_neut["tone"]})
# gate must NOT override a safety tone (prior already zeroed)
r_safe=pac.compose({"tone":"one_at_a_time_interrupt","pace":"quick"},WARM_DREAM,answer_stance="cautionary")
check("caution_gate_never_touches_safety",
      r_safe["tone"]=="one_at_a_time_interrupt" and r_safe["composition_receipt"]["caution_gate_fired"] is False,
      {"safe_tone":r_safe["tone"]})

# 7b. missing /intent policy fails closed to careful (best-practices contract)
r = pac.compose(None, DREAM)
check("missing_policy_fail_closed", r["tone"] == "memory_uncertain"
      and r["composition_receipt"]["class"] == "missing_policy_fail_closed"
      and r["composition_receipt"]["cue_policy"] == "intent_missing_voice_delivery_policy",
      {"final": r["tone"]})

# 7c. vocabulary compliance: every composer output tone is a member of
# chatterbox ALLOWED_TONES parsed from the presets file on disk (Amendment 1).
import ast, os
presets_path = os.path.expanduser(
    "~/workspace/experiments/chatterbox/src/chatterbox/agent/presets.py")
tree = ast.parse(open(presets_path).read())
allowed = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "ALLOWED_TONES":
        allowed = set(ast.literal_eval(node.value))
outputs = {t for fams in pac.TAG_FAMILY_TONE.values() for t, _ in fams.values()}
outputs |= {t for t, _ in pac.TAG_FLOOR_TONE.values()}
outputs.add(pac.MISSING_POLICY_TONE[0])
check("output_vocabulary_in_chatterbox_allowed_tones",
      allowed is not None and outputs <= allowed,
      {"outputs": sorted(outputs),
       "outside_allowed": sorted(outputs - (allowed or set()))})

# 7. provenance always present
check("provenance_present", all(
    pac.compose({"tone": t}, DREAM)["composition_receipt"]["dream_provenance"]["dream_node_key"] == "dream_fixture"
    for t in ("deflect_calm", "memory_confident", "one_at_a_time_interrupt")), {})

receipt = {"schema": "persona_dream.composer_probe_receipt.v1",
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "gate_source": "persona_affect_composer.compose (real function)",
           "cases": cases, "passed": ok}
out = ROOT / "reports/goal_v4/composer_probe_receipt.v1.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"passed": ok, "cases": {k: v["passed"] for k, v in cases.items()}}, indent=2))
sys.exit(0 if ok else 1)
