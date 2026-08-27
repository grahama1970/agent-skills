#!/usr/bin/env python3
"""curate-client: client KB curation pipeline (stdlib only).

Subcommands: plan | chunks | ingest | verify | prep-pack | build
Fail-closed: missing required config emits curate_client.needs_interview.v1.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

MEMORY_REPO = Path.home() / "workspace/experiments/memory"


def _load_config(path: str) -> dict:
    text = Path(path).read_text()
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ModuleNotFoundError:
        # minimal YAML subset: key: value, key:\n  - item
        cfg: dict = {}
        key = None
        for line in text.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            m = re.match(r"^(\w+):\s*(.*)$", line)
            if m:
                key = m.group(1)
                val = m.group(2).strip()
                cfg[key] = val if val else []
            elif line.strip().startswith("- ") and key:
                cfg.setdefault(key, [])
                if isinstance(cfg[key], list):
                    cfg[key].append(line.strip()[2:].strip())
        return cfg


def _needs_interview(missing: list[str]) -> None:
    print(json.dumps({
        "schema": "curate_client.needs_interview.v1",
        "status": "NEEDS_INTERVIEW",
        "missing_fields": missing,
        "next_action": "Run $interview to collect the missing fields; do not guess.",
    }, indent=1))
    sys.exit(3)


def _validate(cfg: dict) -> None:
    missing = [k for k in ("client", "kb_root") if not cfg.get(k)]
    if not (cfg.get("openapi_specs") or cfg.get("terraform_repos")):
        missing.append("openapi_specs|terraform_repos")
    if missing:
        _needs_interview(missing)


def _prep_pack_path(cfg: dict) -> Path:
    value = cfg.get("live_evidence_prep_pack")
    if not value:
        _needs_interview(["live_evidence_prep_pack"])
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        print(json.dumps({
            "schema": "curate_client.prep_pack_missing.v1",
            "status": "FAIL",
            "path": str(path),
            "next_action": "Create a live_evidence.prep_pack.v1 file or update live_evidence_prep_pack in the client config.",
        }, indent=1))
        sys.exit(1)
    return path


def extract_openapi(spec_path: str, outdir: Path, client: str) -> int:
    spec = Path(spec_path).read_text()
    n = 0
    if "\npaths:\n" in spec:
        body = spec.split("\npaths:\n", 1)[1].split("\ncomponents:", 1)[0]
        for b in re.split(r"^(?=  /)", body, flags=re.M):
            m = re.match(r"  (/[^\s:]+):", b)
            if not m:
                continue
            path = m.group(1)
            for mm in re.finditer(r"^    (get|post|put|patch|delete):\n((?:      .*\n)+)", b, re.M):
                method, mb = mm.group(1).upper(), mm.group(2)
                summ = re.search(r"summary:\s*(.+)", mb)
                s = summ.group(1).strip() if summ else ""
                slug = re.sub(r"[^a-z0-9]+", "-", f"{method}-{path}".lower()).strip("-")[:80]
                q = f"How do you {s.lower() or 'call ' + path} via the {client} API?"
                lines = [f"# {method} {path}", "", f"Q: {q}", "",
                         f"A: {client} API: `{method} {path}`" + (f" — {s}." if s else "."),
                         f"Source: {spec_path}"]
                (outdir / "endpoints").mkdir(parents=True, exist_ok=True)
                (outdir / "endpoints" / f"{slug}.md").write_text("\n".join(lines) + "\n")
                n += 1
    if "\ncomponents:" in spec:
        comp = spec.split("\ncomponents:", 1)[1]
        sch = comp.split("  schemas:\n", 1)[1] if "  schemas:\n" in comp else comp
        for b in re.split(r"^(?=    [A-Za-z][\w.-]*:\s*$)", sch, flags=re.M):
            m = re.match(r"    ([A-Za-z][\w.-]*):", b)
            if not m:
                continue
            name = m.group(1)
            props = re.findall(r"^        (\w+):\s*$", b, re.M)
            enum_m = re.findall(r"^\s+enum:\n((?:\s+- .+\n)+)", b, re.M)
            lines = [f"# Schema: {name}", "",
                     f"Q: What is the {name} object in the {client} API and what fields does it have?",
                     "", f"A: `{name}`."]
            if props:
                lines.append("Fields: " + ", ".join(props[:40]) + ".")
            for em in enum_m[:3]:
                vals = [v.strip("- ").strip() for v in em.strip().splitlines()]
                lines.append("Enum values: " + ", ".join(vals[:25]) + ".")
            lines.append(f"Source: {spec_path} components.schemas")
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:70]
            (outdir / "schemas").mkdir(parents=True, exist_ok=True)
            (outdir / "schemas" / f"{slug}.md").write_text("\n".join(lines) + "\n")
            n += 1
    return n


def extract_terraform(repo: str, outdir: Path, client: str) -> int:
    n = 0
    base = Path(repo)
    for vf in base.rglob("variables.tf"):
        txt = vf.read_text(errors="ignore")
        for m in re.finditer(r'variable\s+"(\w+)"\s*\{([^}]*)\}', txt, re.S):
            name, body = m.group(1), m.group(2)
            desc = re.search(r'description\s*=\s*"([^"]*)"', body)
            lines = [f"# {base.name}: variable {name}", "",
                     f"Q: What does the `{name}` variable configure in {client}'s {base.name}?",
                     "", f"A: {desc.group(1)[:250] if desc else 'Terraform input variable.'}",
                     f"Source: {base.name} {vf.relative_to(base)}"]
            slug = re.sub(r"[^a-z0-9]+", "-", f"{base.name}-{name}".lower()).strip("-")[:70]
            (outdir / "infra").mkdir(parents=True, exist_ok=True)
            (outdir / "infra" / f"{slug}.md").write_text("\n".join(lines) + "\n")
            n += 1
    return n


def cmd_chunks(cfg: dict) -> dict:
    outdir = Path(cfg["kb_root"]) / "knowledge"
    outdir.mkdir(parents=True, exist_ok=True)
    total = 0
    for spec in cfg.get("openapi_specs") or []:
        total += extract_openapi(spec, outdir, cfg["client"])
    for repo in cfg.get("terraform_repos") or []:
        total += extract_terraform(repo, outdir, cfg["client"])
    return {"chunks_written": total, "knowledge_dir": str(outdir)}


def cmd_ingest(cfg: dict) -> dict:
    scope = f"client:{cfg['client']}"
    code = (
        "import json;from typer.testing import CliRunner;"
        "from graph_memory.workspace.ingest import app;"
        f"r=CliRunner().invoke(app,[{json.dumps(cfg['kb_root'])},'--scope',{json.dumps(scope)}]);"
        "out=r.output;print(out[out.index('{'):])"
    )
    proc = subprocess.run(
        ["uv", "run", "--all-extras", "python", "-c", code],
        cwd=MEMORY_REPO, capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0:
        return {"status": "FAIL", "stderr": proc.stderr[-500:]}
    out = json.loads(proc.stdout[proc.stdout.index("{"):])
    return {"status": "ok", "scope": scope, "meta": out.get("meta")}


def cmd_verify(cfg: dict) -> dict:
    daemon = cfg.get("memory_daemon") or "http://127.0.0.1:8601"
    results = []
    ok = True
    for probe in cfg.get("probes") or []:
        req = urllib.request.Request(
            daemon + "/recall",
            data=json.dumps({"q": f"{cfg['client']} {probe}", "limit": 3}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=30).read())
            hit = bool(d.get("found")) and any(
                cfg["client"].lower() in json.dumps(i).lower() for i in d.get("items", []))
        except Exception as exc:  # daemon down => fail closed with the reason
            results.append({"probe": probe, "error": str(exc)[:120]})
            ok = False
            continue
        results.append({"probe": probe, "found": d.get("found"), "client_hit": hit,
                        "confidence": d.get("confidence")})
        ok = ok and hit
    return {"status": "PASS" if ok and results else "FAIL", "probes": results}


def cmd_prep_pack(cfg: dict) -> dict:
    path = _prep_pack_path(cfg)
    payload = json.loads(path.read_text())
    if payload.get("schema") != "live_evidence.prep_pack.v1":
        return {
            "schema": "curate_client.prep_pack_receipt.v1",
            "status": "FAIL",
            "path": str(path),
            "error": "prep pack schema must be live_evidence.prep_pack.v1",
        }
    payload.setdefault("producer", {
        "skill": "curate-client",
        "client_scope": f"client:{cfg['client']}",
        "kb_root": cfg["kb_root"],
        "knowledge_dir": str(Path(cfg["kb_root"]) / "knowledge"),
        "live_evidence_repos_append": cfg["kb_root"],
    })
    return {
        "schema": "curate_client.prep_pack_receipt.v1",
        "status": "PASS",
        "client": cfg["client"],
        "scope": f"client:{cfg['client']}",
        "path": str(path),
        "prep_pack": payload,
    }




# Systems detectable in a built KB, mapped to the owner-team collaboration
# point and the coverage question the engagement must answer in advance.
COLLABORATION_SIGNALS = {
    "terraform": ("infrastructure/platform team",
                  "Which Terraform surfaces exist (CLI modules, HCP org, registry) and can a read token be minted in advance?"),
    "okta": ("identity team",
             "Which identity provider fronts the client, and is an org domain available for read-only OIDC discovery probes?"),
    "oidc": ("identity team",
             "Can token verification be demonstrated against their JWKS without credentials?"),
    "sqs": ("event-platform team",
            "Which event topics exist, what are the redelivery/ordering semantics, and is a sandbox queue available?"),
    "kubernetes": ("platform team",
                   "Which cluster/deploy flow (EKS, ArgoCD, Spacelift) would an agent workload join, and who approves?"),
    "eks": ("platform team",
            "How do workloads get AWS credentials (IRSA?) and who owns the role definitions?"),
    "kyc": ("compliance team",
            "Which data boundaries apply to KYC/PII material in prompts, logs, and evaluation fixtures?"),
    "openapi": ("API platform team",
                "Which API tiers are public vs authenticated, and what is the token lead time for a sandbox credential?"),
}


def cmd_research_plan(cfg: dict) -> dict:
    knowledge = Path(cfg["kb_root"]) / "knowledge"
    corpus = ""
    for f in list(knowledge.rglob("*.md"))[:2000]:
        try:
            corpus += f.read_text(errors="ignore").lower()
        except OSError:
            continue
    hits = {k: v for k, v in COLLABORATION_SIGNALS.items() if k in corpus}
    questions = [
        {"id": f"coverage-{key}", "header": key[:12],
         "text": q, "options": []}
        for key, (_team, q) in hits.items()
    ]
    plan = {
        "schema": "curate_client.research_plan.v1",
        "client": cfg["client"],
        "collaboration_points": [
            {"system": k, "owner_team": team, "coverage_question": q}
            for k, (team, q) in hits.items()
        ],
        "interview_packet": {"title": f"{cfg['client']} coverage interview",
                             "questions": questions},
        "deep_research_directives": {
            "brave_search_concurrent": [
                f"{cfg['client']} {k} architecture" for k in hits
            ] + [f"{cfg['client']} engineering blog",
                 f"{cfg['client']} CTO OR 'VP engineering' talk"],
            "fetcher_or_surf_sites": [
                "client developer docs and llms.txt index",
                "client engineering blog posts found by brave",
            ],
            "github_search_or_gh": [
                f"org:{cfg['client']} repos, languages, infra forks",
                f"{cfg['client']} in READMEs of popular integration repos",
            ],
            "ingest_youtube": [
                f"{cfg['client']} conference talks and executive speeches",
                f"{cfg['client']} engineering deep-dive videos",
            ],
            "webgpt_deep_seat": [
                f"expected interview/meeting questions about {cfg['client']} {k}"
                for k in list(hits)[:4]
            ],
            "note": "brave queries run concurrently; each modality is blind to the others (multi-modal sweep); results feed chunks then re-run research-plan",
        },
        "note": "Deterministic derivation from the built KB; agentic research is delegated to the named skills. Empty hits mean the KB is too thin to plan from - build first.",
    }
    if not hits:
        plan["status"] = "FAIL"
        plan["failure_code"] = "kb_too_thin_for_research_plan"
        return plan
    plan["status"] = "PASS"
    return plan


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: curate.py plan|chunks|ingest|verify|prep-pack|build --config <yaml>", file=sys.stderr)
        sys.exit(2)
    cmd = sys.argv[1]
    if "--config" not in sys.argv:
        _needs_interview(["config"])
    cfg = _load_config(sys.argv[sys.argv.index("--config") + 1])
    _validate(cfg)
    if cmd == "plan":
        out = {"client": cfg["client"], "kb_root": cfg["kb_root"],
               "openapi_specs": cfg.get("openapi_specs") or [],
               "terraform_repos": cfg.get("terraform_repos") or [],
               "scope": f"client:{cfg['client']}", "writes": False}
    elif cmd == "chunks":
        out = cmd_chunks(cfg)
    elif cmd == "ingest":
        out = cmd_ingest(cfg)
    elif cmd == "verify":
        out = cmd_verify(cfg)
    elif cmd == "research-plan":
        out = cmd_research_plan(cfg)
    elif cmd == "prep-pack":
        out = cmd_prep_pack(cfg)
    elif cmd == "build":
        out = {"chunks": cmd_chunks(cfg), "ingest": cmd_ingest(cfg), "verify": cmd_verify(cfg), "prep_pack": cmd_prep_pack(cfg)}
        out["status"] = out["verify"]["status"]
    else:
        print(f"unknown command {cmd}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(out, indent=1))
    if isinstance(out, dict) and out.get("status") == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
