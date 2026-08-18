#!/usr/bin/env bash
# Retained negative controls for the claim/evidence/regression/coverage gates
# (#1445-#1448). Every check is a real run of run.sh against a committed or
# temp fixture, read back independently -- the gate must turn RED on the
# weakened input, or this script fails. This is the framework proving it cannot
# be gamed, in its own idiom (real runner invocations, not unit tests over the
# code that authored them).
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
R="$SKILL_DIR/run.sh"
PY() { python3 -c "$1"; }
ok() { echo "  ok: $1"; }

echo "== #1445/#1446: evidence-class separation (committed selftest fixtures) =="
"$R" run "$SKILL_DIR/fixtures/selftest/det_only_missing_live.json" --report-only 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin);c=d['capability_readiness']['claims'][0]
assert d['readiness']!='READY' and c['verdict']=='PARTIALLY_PROVEN' and c['missing_evidence']==['live_e2e'],d
"; ok "deterministic passes cannot satisfy required live_e2e"

"$R" run "$SKILL_DIR/fixtures/selftest/live_proven.json" --report-only 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin);c=d['capability_readiness']['claims'][0]
assert d['readiness']=='READY' and c['verdict']=='PROVEN',d
"; ok "adding the qualifying live case with readback flips the same claim to READY"

"$R" run "$SKILL_DIR/fixtures/selftest/pseudo_live.json" --report-only 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin);case=d['cases'][0]
assert case['live_qualified'] is False and case['effective_evidence_class']=='fault_injected_deterministic' and d['readiness']!='READY',d
"; ok "live_e2e with no independent readback is downgraded, cannot satisfy live"

"$R" run "$SKILL_DIR/fixtures/selftest/blocked_live.json" --report-only 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin);c=d['capability_readiness']['claims'][0]
assert d['cases'][0]['outcome']=='BLOCKED' and c['verdict']=='BLOCKED_EXTERNAL' and d['readiness']!='READY',d
"; ok "BLOCKED_EXTERNAL live case never reaches capability READY"

"$R" run "$SKILL_DIR/fixtures/selftest/exemption.json" --report-only 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin);m={c['id']:c for c in d['capability_readiness']['claims']}
v=m['demo.exempt.valid'];e=m['demo.exempt.expired']
assert v['verdict']!='PROVEN' and v['exempt_evidence']==['live_e2e'],v
assert e['exempt_evidence']==[] and 'live_e2e' in e['missing_evidence'],e
assert d['readiness']!='READY'
"; ok "valid exemption is visible but not PROVEN; expired exemption is ignored"

echo "== #1447: regression lifecycle =="
"$R" regressions verify "$SKILL_DIR" --report-only 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin)
assert d['verified']==5 and d['unproven']==0 and d['no_proof_command']==0,d
"; ok "all 5 committed regressions verify fail-before-fix (guards are non-vacuous)"

# Mutation A: rename the retained case -> audit reports the invariant UNPROTECTED.
TS="$(mktemp -d)"; mkdir -p "$TS/fixtures"
cp "$SKILL_DIR/fixtures/agentic_eval.json" "$TS/fixtures/agentic_eval.json"
PY "
import json
p='$TS/fixtures/regressions.json'
reg={'schema':'agentic_evals.regressions.v1','version':1,'skill':'t','regressions':[
 {'regression_id':'r1','retained_case':'DOES-NOT-EXIST','retained_fixture':'agentic_eval.json',
  'evidence_class':'fault_injected_deterministic','status':'ACTIVE',
  'fail_before_fix':{'proven':True}}]}
open(p,'w').write(json.dumps(reg))
"
"$R" regressions show "$TS" 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin);r=d['regressions'][0]
assert r['protected'] is False and d['summary']['unprotected']==1,d
assert any('UNPROTECTED' in i for i in r['issues']),r
"; ok "renaming the retained case makes the audit report the regression UNPROTECTED"

# Mutation B: drop fail_before_fix -> never-proven (possibly vacuous).
PY "
import json
p='$TS/fixtures/regressions.json'
reg=json.load(open(p));reg['regressions'][0]['retained_case']='happy-path'  # any missing is fine; test establishment separately
reg['regressions'][0].pop('fail_before_fix',None)
open(p,'w').write(json.dumps(reg))
"
"$R" regressions show "$TS" 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin)
assert d['summary']['never_proven_fail_before_fix']==1,d
"; ok "a regression with no fail_before_fix proof is flagged never-proven (not established)"

# Mutation C: a vacuous guard (proof exits 0 while expected_fail) fails verification.
PY "
import json
p='$TS/fixtures/regressions.json'
reg={'schema':'agentic_evals.regressions.v1','version':1,'skill':'t','regressions':[
 {'regression_id':'vacuous','retained_case':'x','retained_fixture':'agentic_eval.json',
  'evidence_class':'fault_injected_deterministic','status':'ACTIVE',
  'fail_before_fix':{'proven':True,'expected_fail':True,'proof_command':['bash','-c','true']}}]}
open(p,'w').write(json.dumps(reg))
"
set +e
VOUT="$("$R" regressions verify "$TS" 2>/dev/null)"; RC=$?
set -e
echo "$VOUT" | PY "
import json,sys;d=json.load(sys.stdin)
assert d['unproven']==1 and d['verified']==0,d
"
test $RC -ne 0; ok "a vacuous guard is reported unproven AND makes verify exit non-zero"

echo "== #1448: seam-coverage sufficiency cannot be gamed =="
# A skill with one uncovered critical seam -> NOT_READY, gap names the seam.
US="$(mktemp -d)"; mkdir -p "$US/fixtures"
PY "
import json
fx={'version':2,'skill':'u','seams':[
  {'seam_id':'covered.seam','claim_id':'c1','seam_type':'filesystem/process','criticality':'critical','required_evidence':['fault_injected_deterministic']},
  {'seam_id':'UNCOVERED.seam','claim_id':'c2','seam_type':'browser/UI transport','criticality':'critical','required_evidence':['live_e2e']}],
 'cases':[{'name':'c-1','type':'adversarial','evidence_class':'fault_injected_deterministic','seams':['covered.seam'],
           'command':['bash','run.sh'],'expected':{'exit_code':0,'stdout_contains':['x']}}]}
open('$US/fixtures/agentic_eval.json','w').write(json.dumps(fx))
"
"$R" coverage show "$US" 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin)
assert d['summary']['verdict']=='NOT_READY',d['summary']
assert 'UNCOVERED.seam' in d['summary']['highest_priority_gaps'],d['summary']
"; ok "an uncovered critical seam is identified by exact seam_id"

# Anti-gaming: pile 12 duplicate smoke cases onto the COVERED seam -> the
# uncovered seam does not disappear.
PY "
import json
p='$US/fixtures/agentic_eval.json';fx=json.load(open(p))
for i in range(12):
    fx['cases'].append({'name':'smoke-%d'%i,'type':'positive','seams':['covered.seam'],
                        'command':['bash','run.sh'],'expected':{'exit_code':0}})
open(p,'w').write(json.dumps(fx))
"
"$R" coverage show "$US" 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin)
assert d['summary']['verdict']=='NOT_READY' and 'UNCOVERED.seam' in d['summary']['highest_priority_gaps'],d['summary']
"; ok "12 duplicate smoke cases on another seam cannot fill the uncovered seam"

# Weak-only coverage (bare exit 0 positive) does not count as covering a seam.
WS="$(mktemp -d)"; mkdir -p "$WS/fixtures"
PY "
import json
fx={'version':2,'skill':'w','seams':[
  {'seam_id':'s1','claim_id':'c1','seam_type':'filesystem/process','criticality':'critical','required_evidence':['fault_injected_deterministic']}],
 'cases':[{'name':'smoke','type':'positive','seams':['s1'],'command':['bash','run.sh'],'expected':{'exit_code':0}}]}
open('$WS/fixtures/agentic_eval.json','w').write(json.dumps(fx))
"
"$R" coverage show "$WS" 2>/dev/null | PY "
import json,sys;d=json.load(sys.stdin);s=d['seams'][0]
assert s['weak_only'] is True and s['covered'] is False and d['summary']['verdict']=='NOT_READY',d
"; ok "a bare exit-0 smoke case is weak-only and does not cover its seam"

echo "ALL HARDENING SELFTESTS PASSED"
