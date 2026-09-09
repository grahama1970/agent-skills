"""Regression: quoted verdicts must not override the declared verdict (2026-09-09)."""
import re, sys
import pathlib; scripts = str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'); sys.path.insert(0, scripts)
spec = open(pathlib.Path(scripts) / 'tau_roundtable_worker.py').read()
ns = {'re': re}
# extract just the regex + function to avoid importing the whole worker
start = spec.index('_VERDICT_LINE_RE')
end = spec.index('def _has_verdict')
exec(spec[start:end], ns)
_extract = ns['_extract_verdict']

_real = pathlib.Path('/home/graham/.local/state/project-watchdog/receipts/project-watchdog-20260909T135501Z-201cb3190700/ask/ask-tau-repair-grahama1970-agent-skills--3ab1466ccce9/node-artifacts/handler-codex/response.md')
if _real.is_file():  # retained real receipt from the 2026-09-09 incident, when present
    assert _extract(_real.read_text()) == 'PASS'

assert _extract('VERDICT: PASS') == 'PASS'
assert _extract('VERDICT: FAIL') == 'FAIL'
assert _extract('blah\nVERDICT: NEEDS_ATTENTION\n') == 'NEEDS_ATTENTION'
# quoted historical verdict does not win
assert _extract('context: REVIEW VERDICT: NEEDS_ATTENTION was seen\nVERDICT: PASS') == 'PASS'
# last declared verdict wins
assert _extract('VERDICT: FAIL\nafter rework\nVERDICT: PASS') == 'PASS'
# inline fallback still works
assert _extract('the result is VERDICT: PASS today') == 'PASS'
assert _extract('no verdict here') is None
print('ALL VERDICT EXTRACTION CASES PASS (incl. real 1628 receipt)')
