import json
from pathlib import Path
def generate(work_dir, params):
    root = Path(work_dir); root.mkdir(parents=True, exist_ok=True)
    for i, rep in enumerate(["str", "int"]):
        d = root / f"case-{rep}"; (d / "corpus").mkdir(parents=True)
        (d / "policy.json").write_text(json.dumps({"version":1,"protected_values":[],
            "sensitive_values":[{"rule_id":"r","subject_id":"s","type":"name","value":"5551234567"}]}))
        v = "5551234567" if rep == "str" else 5551234567
        (d / "corpus" / "d.json").write_text(json.dumps({"v": v}))
        yield f"case-{rep}", str(d)
