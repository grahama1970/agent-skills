"""Deterministic evaluator positive + negative assertions (offline)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluators import eval_json_output, eval_python_code

# positive
assert eval_json_output('{"a":1,"b":2}', expected_keys={"a","b"})[0] == 3
assert eval_python_code("def f(x):\n return x+1", "assert f(1)==2")[0] == 3
assert eval_json_output('```json\n{"a":1}\n```', expected_keys={"a"})[0] == 3  # fenced
# negative / adversarial
assert eval_json_output("not json", expected_keys={"a"})[0] == 0
assert eval_python_code("def f(x):\n return x", "assert f(1)==2")[0] == 1  # assertion fail
assert eval_json_output('{"timeout":"120 second"}', expected_json={"timeout":120})[0] == 1  # wrong value
print("EVALUATORS_OK positive+negative")
