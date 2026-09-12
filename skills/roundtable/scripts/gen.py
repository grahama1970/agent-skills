#!/usr/bin/env python3
"""Emit a pi-subagents workflowScript for roundtable/compete with first-class web models."""
import argparse, json, sys, pathlib

FANOUTS = {
 "roundtable": """const results = await runs.all(SEATS.map(s => ({ key: s.key, agent: s.agent, model: s.model, task: PACKET + '\\n\\nYou are seat ' + s.key + ' in a concurrent roundtable. Answer independently; other seats cannot see you.' })).concat(webRuns).concat(researchRuns));
const join = await runs.run({ key: 'join', agent: 'reviewer', model: 'anthropic/claude-opus-4-8:high',
  task: 'Synthesize these roundtable responses into one answer with attributed agreements, disagreements, and dissent preserved by seat key.\\n\\n' + JSON.stringify(results) });
return { seats: results, synthesis: join };""",
 "compete": """const candidates = await runs.all(SEATS.map(s => ({ key: s.key, agent: s.agent, model: s.model,
  task: 'COMPETITION BRIEF: ' + TASK + '\\n\\nYou are competing against other models you cannot see. Maximize: ' + CRITERION })).concat(webRuns).concat(researchRuns));
const verdict = await runs.run({ key: 'judge', agent: 'reviewer', model: 'anthropic/claude-opus-4-8:high',
  task: 'Judge this model competition. Criterion: ' + CRITERION + '. Score each candidate, name exactly one winner, state what losers missed. Return a scorecard.\\n\\n' + JSON.stringify(candidates) });
return { candidates, verdict };""",
}
AGENT_FOR = {"reviewer": "reviewer", "general-purpose": "general-purpose"}
WEB_ALLOWED = {"webgpt", "webclaude", "webkimi", "webgemini", "webgrok", "webperplexity", "cursor-browser"}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=list(FANOUTS))
    p.add_argument("--packet-file")
    p.add_argument("--packet")
    p.add_argument("--seat", action="append", default=[], metavar="KEY[=AGENT]=MODEL",
                   help="e.g. gpt=openai-codex/gpt-5.5:high or opus:reviewer=anthropic/claude-opus-4-8:high")
    p.add_argument("--web", action="append", default=[], help="$ask browser backend: webgpt webkimi webgemini webgrok webperplexity webclaude")
    p.add_argument("--web-research", action="append", default=[], metavar="KEY", help="pi-web-access research seat key(s)")
    p.add_argument("--criterion", default="concrete, code-grounded, actionable")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    if bool(a.packet_file) == bool(a.packet): sys.exit("exactly one of --packet-file / --packet")
    packet = pathlib.Path(a.packet_file).read_text() if a.packet_file else a.packet
    seats = []
    for spec in a.seat:
        key, _, rest = spec.partition("=")
        agent, _, model = rest.partition("=")
        if not model: agent, model = "reviewer", rest
        if agent not in AGENT_FOR: sys.exit("unknown agent " + agent)
        seats.append({"key": key, "agent": agent, "model": model})
    for b in a.web:
        if b not in WEB_ALLOWED: sys.exit("unknown web backend " + b + "; allowed: " + " ".join(sorted(WEB_ALLOWED)))
    if not seats and not a.web and not a.web_research:
        sys.exit("fail-closed: no seats (need --seat, --web, or --web-research)")
    t = pathlib.Path(__file__).parent.parent / "templates" / "workflow.template.js"
    js = t.read_text()
    packet_js = json.dumps(packet) if a.mode == "roundtable" else json.dumps(packet)
    js = (js.replace("__MODE__", a.mode)
            .replace("__PACKET__", "PACKET = " + packet_js)
            .replace("__CRITERION__", "CRITERION = " + json.dumps(a.criterion) + ("; const TASK = PACKET" if a.mode == "compete" else ""))
            .replace("__SEATS__", json.dumps(seats, indent=2))
            .replace("__WEB__", json.dumps(a.web))
            .replace("__WEBRESEARCH__", json.dumps(a.web_research))
            .replace("__FANOUT__", FANOUTS[a.mode])
            .replace("__OUT__", a.out))
    pathlib.Path(a.out).write_text(js)
    print(json.dumps({"out": a.out, "mode": a.mode, "seats": [s["key"] for s in seats], "web": a.web, "web_research": a.web_research,
                      "load": "subagent({workflowScriptPath:'%s', async:true})" % a.out}))
if __name__ == "__main__":
    main()
