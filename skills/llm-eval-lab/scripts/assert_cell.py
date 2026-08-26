"""Assert a run-matrix result file has a real scored cell with a receipt."""
import json, sys
d = json.load(open(sys.argv[1]))
assert d["status"] == "complete", f"status={d['status']}"
ok = [r for r in d["results"]
      if r["status"] != "INFRA_BLOCKED" and r["pass_at_1"] is not None and r["trials"][0].get("run_dir")]
assert ok, "no real scored cell with an on-disk run_dir receipt"
print("RUN_MATRIX_CELL_OK", ok[0]["model"], "pass@1", ok[0]["pass_at_1"])
