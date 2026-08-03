#!/usr/bin/env bash
# Behavioral gates for goal-drift: positive, negative, adversarial, safety.
unset VIRTUAL_ENV
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PYTHONPATH="$ROOT/src" python3 - <<'PY'
import sys
sys.path.insert(0, "src")
from goal_drift.core import (Action, Criterion, GoalRecord, GoalRegistrationError,
                             GoalSource, INDIRECT_CAP, RunVerdict, Verdict, audit)

fails = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else ' :: ' + detail}")
    if not cond: fails.append(name)

REPORT = Criterion(key="report", text="daily interactive report",
                   artifact_globs=("**/report*.html",), keywords=("interactive report",))
RESUME = Criterion(key="resume", text="tailored resume variant",
                   artifact_globs=("**/resume-*.docx",), keywords=("tailored resume",))
def goal(*crit):
    return GoalRecord(project="p", goal_text="Deliver a daily interactive opportunity report each morning.",
                      source=GoalSource.HUMAN_PROMPT, criteria=crit or (REPORT,)).validate()

print("== positive control: work matching a criterion is SERVES_GOAL ==")
a = audit(goal(), [Action("artifact", "a1", "built interactive report", ("out/report.html",))], "24h")
check("verdict ON_GOAL", a.run_verdict is RunVerdict.ON_GOAL, a.run_verdict.value)
check("labeled SERVES_GOAL", any(f.verdict is Verdict.SERVES_GOAL for f in a.findings))

print("== absence is a finding: 12 commits, zero required artifacts ==")
acts = [Action("commit", f"c{i}", "refactor internals", ("src/x.py",)) for i in range(12)]
a = audit(goal(), acts, "24h")
check("verdict DRIFTED", a.run_verdict is RunVerdict.DRIFTED, a.run_verdict.value)
check("MISSING_EXPECTED present", any(f.verdict is Verdict.MISSING_EXPECTED for f in a.findings))

print("== the real 2026-08-02 case: productive night, wrong work ==")
real = [Action("commit","t1","fix dag reachability in tau compiler",("src/tau/compiler.py",)),
        Action("commit","d1","add four sections to ask SKILL.md",("skills/ask/SKILL.md",)),
        Action("commit","r1","repair recall.py truncation",("src/graph_memory/recall.py",))]
a = audit(goal(REPORT, RESUME), real, "24h")
check("verdict DRIFTED", a.run_verdict is RunVerdict.DRIFTED, a.run_verdict.value)
check("both absences reported",
      sum(1 for f in a.findings if f.verdict is Verdict.MISSING_EXPECTED) == 2)

print("== adversarial: unlimited 'groundwork' cannot pass ==")
ground = [Action("commit", f"g{i}", "necessary groundwork", ("src/infra.py",)) for i in range(10)]
a = audit(goal(), ground + [Action("artifact","ok","interactive report",("out/report.html",))], "24h")
check("groundwork commits flagged UNTICKETED_WORK",
      sum(1 for f in a.findings if f.verdict is Verdict.UNTICKETED_WORK) == 10)
check("verdict DRIFTED despite one real hit", a.run_verdict is RunVerdict.DRIFTED, a.run_verdict.value)

print("== indirect cap: many on-criterion tickets, none carrying proof ==")
# SUPPORTS_INDIRECTLY now means: on-criterion but unproven. Unlimited 'in progress'
# must not read as on-goal either.
from goal_drift.evidence import Ticket as _T
wip = [_T(number=100+i, title="daily interactive report wip", state="OPEN",
          body="in progress", has_proof=False) for i in range(9)]
done = _T(number=99, title="daily interactive report", state="CLOSED",
          body="Proof: run.sh report", has_proof=True)
a = audit(goal(), [], "24h", tickets=wip + [done])
check("share exceeds cap", a.indirect_share > INDIRECT_CAP, f"{a.indirect_share:.2f}")
check("verdict DRIFTED on unproven pile", a.run_verdict is RunVerdict.DRIFTED, a.run_verdict.value)

print("== no goal is NOT_ESTABLISHED, never on-track ==")
a = audit(None, [], "24h", project="p")
check("verdict NOT_ESTABLISHED", a.run_verdict is RunVerdict.NOT_ESTABLISHED)
check("never reports ON_GOAL", a.run_verdict is not RunVerdict.ON_GOAL)
check("GOAL_UNREGISTERED finding", any(f.verdict is Verdict.GOAL_UNREGISTERED for f in a.findings))

print("== no self-certification: agent_inferred goals refused ==")
try:
    GoalRecord(project="p", goal_text="a"*40, source=GoalSource.AGENT_INFERRED,
               criteria=(REPORT,)).validate()
    check("refuses agent_inferred", False, "accepted")
except GoalRegistrationError:
    check("refuses agent_inferred", True)

print("== a goal with no criteria is refused (absence would be undetectable) ==")
try:
    GoalRecord(project="p", goal_text="a"*40, source=GoalSource.HUMAN_PROMPT, criteria=()).validate()
    check("refuses criteria-less goal", False, "accepted")
except GoalRegistrationError:
    check("refuses criteria-less goal", True)

print("== report leads with verdict and absences, not volume ==")
txt = audit(goal(REPORT, RESUME), real, "24h").render().splitlines()
check("line 1 states verdict", "verdict:" in txt[0], txt[0])
check("absence precedes serves", "MISSING_EXPECTED" in txt[1], txt[1] if len(txt)>1 else "")


print("== TICKET-FIRST: a ticket declaring off-goal work is DECLARED_DRIFT ==")
sys.path.insert(0, "src")
from goal_drift.evidence import Ticket, commit_references_ticket
off = Ticket(number=1123, title="Fix DAG reachability in tau compiler", state="OPEN",
             labels=("agent-bug",), body="entry_node_ids single root")
a = audit(goal(), [], "24h", tickets=[off])
check("DECLARED_DRIFT on off-goal ticket",
      any(f.verdict is Verdict.DECLARED_DRIFT for f in a.findings))
check("caught at declaration, before any commit", a.run_verdict is RunVerdict.DRIFTED)

print("== closed ticket WITH proof is real acceptance evidence ==")
good = Ticket(number=9, title="Ship daily interactive report", state="CLOSED",
              labels=("agent-work",), body="Proof: run.sh report --json", has_proof=True)
a = audit(goal(), [], "24h", tickets=[good])
check("SERVES_GOAL via attached proof",
      any(f.verdict is Verdict.SERVES_GOAL and f.reason.startswith("closed with attached proof")
          for f in a.findings))
check("absence satisfied by proof", a.run_verdict is RunVerdict.ON_GOAL, a.run_verdict.value)

print("== on-criterion ticket WITHOUT proof does not satisfy absence ==")
noproof = Ticket(number=10, title="Ship daily interactive report", state="OPEN",
                 labels=("agent-work",), body="wip", has_proof=False)
a = audit(goal(), [], "24h", tickets=[noproof])
check("still MISSING_EXPECTED", any(f.verdict is Verdict.MISSING_EXPECTED for f in a.findings))
check("verdict DRIFTED", a.run_verdict is RunVerdict.DRIFTED)

print("== a commit citing no ticket is UNTICKETED_WORK ==")
a = audit(goal(), [Action("commit","c1","refactor internals",("src/x.py",))], "24h",
          tickets=[good])
check("UNTICKETED_WORK flagged", any(f.verdict is Verdict.UNTICKETED_WORK for f in a.findings))

print("== commit citing a ticket resolves to that ticket ==")
t = commit_references_ticket("fix thing (#9)", [good])
check("resolves #9", t is not None and t.number == 9)
check("unknown ref resolves to None", commit_references_ticket("no ref here", [good]) is None)

print("== DEGRADED: a failed evidence source can never read ON_GOAL ==")
a = audit(goal(), [], "24h", tickets=[good], sources_ok={"tickets": False})
check("verdict DEGRADED not ON_GOAL", a.run_verdict is RunVerdict.DEGRADED, a.run_verdict.value)
check("failure named in notes", any("EVIDENCE SOURCE FAILED" in n for n in a.notes))


print("== SEAM CONTRACTS: unignorable, producer-side ==")
from goal_drift.contracts import (AuditContract, SeamViolation, TicketContract, canonical_sha256,
                                  enforce, goal_hash, tau_dag_spec, tau_work_order,
                                  TAU_DAG_SCHEMA, TAU_SKILL_NODE_SCHEMA, TAU_WORK_ORDER_SCHEMA)
from goal_drift.core import goal_to_dict

gp = goal_to_dict(goal())
ok = enforce(AuditContract(audit(goal(), [], "24h", tickets=[good]).to_dict()))
check("valid audit stamped PASS", ok.seam_validation.get("status") == "PASS", str(ok.seam_validation))
check("stamp travels on the payload", ok.payload.get("seam_validation", {}).get("kind") == "goal_drift.audit.v1")

print("== cross-field truth: a lying summary is refused ==")
bad = audit(goal(), [], "24h").to_dict()          # has MISSING_EXPECTED
bad["verdict"] = "ON_GOAL"                         # ...but claims on-goal
try:
    enforce(AuditContract(bad)); check("refuses ON_GOAL contradicting findings", False, "accepted")
except SeamViolation as e:
    check("refuses ON_GOAL contradicting findings", "contradicts" in str(e))

for name, mutate in (
    ("wrong schema", lambda d: d.__setitem__("schema", "nope.v1")),
    ("read_only false", lambda d: d.__setitem__("read_only", False)),
    ("unknown verdict", lambda d: d.__setitem__("verdict", "FINE")),
    ("missing findings", lambda d: d.pop("findings")),
):
    d = audit(goal(), [], "24h", tickets=[good]).to_dict(); mutate(d)
    try:
        enforce(AuditContract(d)); check(f"refuses {name}", False, "accepted")
    except SeamViolation:
        check(f"refuses {name}", True)

print("== NOT_ESTABLISHED must carry its finding ==")
d = audit(None, [], "24h", project="p").to_dict()
check("valid NOT_ESTABLISHED passes", enforce(AuditContract(d)) is not None)
d2 = dict(d); d2["findings"] = []
try:
    enforce(AuditContract(d2)); check("refuses bare NOT_ESTABLISHED", False, "accepted")
except SeamViolation:
    check("refuses bare NOT_ESTABLISHED", True)

print("== ticket ingest: self-heal with record, or raise ==")
t = enforce(TicketContract(number=7, title="x", state="open"))
check("lowercase state self-healed", t.state == "OPEN" and t.repairs, str(t.repairs))
check("status SELF_HEALED", t.seam_validation.get("status") == "SELF_HEALED")
for name, kw in (("bad number", dict(number=0, title="x", state="OPEN")),
                 ("empty title", dict(number=1, title="  ", state="OPEN")),
                 ("bad state", dict(number=1, title="x", state="MERGED"))):
    try:
        enforce(TicketContract(**kw)); check(f"refuses {name}", False, "accepted")
    except SeamViolation:
        check(f"refuses {name}", True)

print("== goal_hash: canonical over CONTENT, immutability provable ==")
h1 = goal_hash(gp)
gp_time = dict(gp); gp_time["registered_at"] = "2099-01-01T00:00:00Z"
check("hash ignores registered_at", goal_hash(gp_time) == h1)
gp_edit = dict(gp); gp_edit["goal_text"] = gp["goal_text"] + " and also refactor everything."
check("hash changes when the goal text changes", goal_hash(gp_edit) != h1)
check("hash is sha256-prefixed", h1.startswith("sha256:"))

print("== tau handoff uses generic_dag_spec.v1, not dag_contract.v1 ==")
spec = tau_dag_spec(run_id="r1", run_dir="/tmp/r1", goal_payload=gp,
                    receipt_path="/tmp/r1/receipt.json", work_order_path="/tmp/r1/wo.json",
                    output_dir="/tmp/r1/out", parent_goal_hash="sha256:older")
check("schema is generic_dag_spec.v1", spec["schema"] == TAU_DAG_SCHEMA, spec["schema"])
check("NOT dag_contract.v1", spec["schema"] != "tau.dag_contract.v1")
check("goal_hash canonical over goal object", spec["goal_hash"] == h1)
check("parent kept as goal.parent_goal_hash",
      spec["goal"]["parent_goal_hash"] == "sha256:older")
check("skill node schema correct", spec["nodes"][0]["skill"]["schema"] == TAU_SKILL_NODE_SCHEMA)
check("node declares read_only", spec["nodes"][0]["skill"]["configuration"]["read_only"] is True)
wo = tau_work_order(gp, "24h")
check("work order schema + hash match", wo["schema"] == TAU_WORK_ORDER_SCHEMA and wo["goal_hash"] == h1)
check("work order forbids mutation in the task text", "Never edit" in wo["task"])

print("== safety: the AUDIT path is write-free ==")
import pathlib, re
MUTATE = (r"open\([^)]*['\"][wax]", r"\.write_text\(", r"\.write_bytes\(",
          r"shutil\.(copy|move|rmtree)", r"os\.(remove|unlink|rename)",
          r"git['\"]?\s*,\s*['\"](commit|push|add|checkout|reset|rm)")
core = pathlib.Path("src/goal_drift/core.py").read_text() + pathlib.Path("src/goal_drift/evidence.py").read_text() + pathlib.Path("src/goal_drift/contracts.py").read_text()
core_bad = [pat for pat in MUTATE if re.search(pat, core)]
check("core.py (audit) has zero mutation calls", not core_bad, str(core_bad))

# The CLI may persist a registered goal, but ONLY under the state registry —
# never into a project tree. Assert every write target derives from REGISTRY.
cli = pathlib.Path("src/goal_drift/cli.py").read_text()
writes = re.findall(r"([A-Za-z_][\w\.\(\)\[\]\"' ]{0,40})\.write_text\(", cli)
check("every CLI write goes through _path()/REGISTRY",
      all("_path(" in w or "REGISTRY" in w for w in writes), str(writes))
check("REGISTRY is under ~/.local/state, not a repo",
      '.local/state/agent-skills/goal-drift' in cli)
cli_bad = [pat for pat in MUTATE if pat != r"\.write_text\(" and re.search(pat, cli)]
check("CLI has no other mutation calls", not cli_bad, str(cli_bad))
# Inspect the actual subprocess argv via AST, not the source text: the word
# "commit" also appears as an Action kind label, which a string match flags falsely.
import ast
MUTATING_GIT = {"commit", "push", "add", "checkout", "reset", "rm", "merge", "rebase", "clean"}
verbs, calls = set(), 0
for mod in ("src/goal_drift/core.py", "src/goal_drift/cli.py", "src/goal_drift/evidence.py"):
    tree = ast.parse(pathlib.Path(mod).read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = ast.unparse(node.func)
        if not fn.startswith("subprocess."):
            continue
        calls += 1
        for arg in node.args:
            if isinstance(arg, (ast.List, ast.Tuple)):
                items = [e.value for e in arg.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if any(i == "git" or i.endswith("/git") for i in items):
                    verbs |= {i for i in items if not i.startswith("-")} - {"git"}
check("subprocess calls found (audit reads git)", calls >= 1, f"calls={calls}")
check("git argv uses no mutating verb", not (verbs & MUTATING_GIT), f"verbs={sorted(verbs)}")
check("git usage is log-only", "\"log\"" in pathlib.Path("src/goal_drift/core.py").read_text())

print("== no direct ArangoDB ==")
arango = [str(p) for p in pathlib.Path("src").rglob("*.py")
          if "ArangoClient" in p.read_text() or "from arango" in p.read_text()]
check("no arango import", not arango, str(arango))

print()
if fails:
    print(f"SANITY FAIL ({len(fails)}): {fails}"); sys.exit(1)
print("SANITY PASS — all behavioral gates green")
PY
