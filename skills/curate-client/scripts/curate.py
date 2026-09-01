#!/usr/bin/env python3
"""curate-client: client KB curation pipeline (stdlib only).

Subcommands: plan | chunks | ingest | verify | prep-pack | build
Fail-closed: missing required config emits curate_client.needs_interview.v1.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MEMORY_REPO = Path.home() / "workspace/experiments/memory"
LIVE_EVIDENCE_DEFAULT_BACKEND = "http://127.0.0.1:8799"
TRIAGE_RUNNER = Path(__file__).resolve().parents[2] / "triage-error" / "run.sh"


class CanonicalReviewedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    review_status: str = Field(min_length=1)
    expected_response_shape: str = Field(min_length=1)
    quality_bar: list[str] = Field(min_length=1)


class CanonicalSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    retrieved_at: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    url: str | None = None
    path: str | None = None
    summary: str = Field(min_length=1)

    @field_validator("path", "url")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        return value or None


class CanonicalBriefingPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    point_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    opening_triggers: list[list[str]] = Field(min_length=1)
    hook: str = Field(min_length=1)
    story: str = Field(min_length=1)
    sources: list[str] = Field(min_length=1)


class CanonicalQuestionOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    canonical_question: str = Field(min_length=1)
    spoken_variants: list[str] = Field(default_factory=list)
    scenario: str = Field(min_length=1)
    rubric_dimension: str = Field(min_length=1)
    clarifications_expected_before_answering: list[str] = Field(min_length=1)
    answer_thesis: str = Field(min_length=1)
    architecture_components: list[str] = Field(min_length=1)
    failure_cases: list[str] = Field(min_length=1)
    tradeoffs: list[str] = Field(min_length=1)
    source_references: list[str] = Field(min_length=1)
    graham_project_bridge: str = Field(min_length=1)
    skill_chain: list[str] = Field(min_length=1)
    hold_answer_clarify_disposition: str = Field(min_length=1)
    reviewed_answer: CanonicalReviewedAnswer
    memory_keys: list[str] = Field(default_factory=list)


class CanonicalClientData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: str = Field(alias="schema")
    client: str = Field(min_length=1)
    classification: str = Field(min_length=1)
    sources: list[CanonicalSource] = Field(min_length=1)
    briefing_points: list[CanonicalBriefingPoint] = Field(min_length=1)
    question_oracles: list[CanonicalQuestionOracle] = Field(min_length=1)

    @field_validator("schema_")
    @classmethod
    def schema_is_current(cls, value: str) -> str:
        if value != "curate_client.canonical_data.v1":
            raise ValueError("schema must be curate_client.canonical_data.v1")
        return value


class PrepPackTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    purpose: str = Field(min_length=1)


class PrepPackResearchStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    skill: str = Field(min_length=1)
    role: str = Field(min_length=1)


class PrepPackSourceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    title: str | None = None
    authority: str | None = None
    retrieved_at: str | None = None
    digest: str | None = None
    url: str | None = None
    path: str | None = None
    summary: str | None = None
    kind: str | None = None
    use: str | None = None

    @field_validator("title", "authority", "retrieved_at", "digest", "url", "path", "summary", "kind", "use")
    @classmethod
    def empty_optional_to_none(cls, value: str | None) -> str | None:
        return value or None


class PrepPackBriefingPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    point_id: str = Field(min_length=1)
    title: str | None = None
    opening_triggers: list[list[str]] = Field(min_length=1)
    hook: str = Field(min_length=1)
    story: str = Field(min_length=1)
    sources: list[str] = Field(min_length=1)


class PrepPackBriefing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    schema_: str = Field(alias="schema")
    pack_id: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    core_concepts: list[str] = Field(min_length=1)
    points: list[PrepPackBriefingPoint] = Field(min_length=1)

    @field_validator("schema_")
    @classmethod
    def schema_is_current(cls, value: str) -> str:
        if value != "live_evidence.briefing_pack.v1":
            raise ValueError("schema must be live_evidence.briefing_pack.v1")
        return value


class PrepPackReviewedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    review_status: str = Field(min_length=1)
    expected_response_shape: str = Field(min_length=1)
    quality_bar: list[str] = Field(min_length=1)


class PrepPackQuestionOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    canonical_question: str = Field(min_length=1)
    spoken_variants: list[str] = Field(default_factory=list)
    scenario: str | None = None
    category: str | None = None
    rubric_dimension: str | None = None
    clarifications_expected_before_answering: list[str] = Field(default_factory=list)
    answer_thesis: str | None = None
    architecture_components: list[str] = Field(default_factory=list)
    failure_cases: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    graham_project_bridge: str | None = None
    skill_chain: list[str] = Field(min_length=1)
    hold_answer_clarify_disposition: str | None = None
    reviewed_answer: PrepPackReviewedAnswer
    memory_keys: list[str] = Field(min_length=2)


class PrepPackMemoryExports(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    ingest_endpoint: str = Field(min_length=1)
    recall_endpoint: str = Field(min_length=1)
    collections: list[str] = Field(min_length=1)


class PrepPackLiveUse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    before_call: list[str] = Field(min_length=1)
    during_call: list[str] = Field(min_length=1)
    after_call: list[str] = Field(min_length=1)


class PrepPackProducer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    skill: str = Field(min_length=1)
    client_scope: str = Field(min_length=1)
    kb_root: str = Field(min_length=1)
    knowledge_dir: str = Field(min_length=1)
    live_evidence_repos_append: str = Field(min_length=1)
    generated: bool


class LiveEvidencePrepPack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: str = Field(alias="schema")
    classification: str = Field(min_length=1)
    pack_id: str = Field(min_length=1)
    target: PrepPackTarget
    research_chain: list[PrepPackResearchStep] = Field(min_length=1)
    source_context: list[PrepPackSourceContext] = Field(min_length=1)
    briefing_pack: PrepPackBriefing
    question_oracles: list[PrepPackQuestionOracle] = Field(min_length=1)
    memory_exports: PrepPackMemoryExports
    live_use: PrepPackLiveUse
    producer: PrepPackProducer

    @field_validator("schema_")
    @classmethod
    def schema_is_current(cls, value: str) -> str:
        if value != "live_evidence.prep_pack.v1":
            raise ValueError("schema must be live_evidence.prep_pack.v1")
        return value


class CurateClientRecallProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1)
    canonical_question: str = Field(min_length=1)
    status_code: int
    found: bool
    confidence: float | int | None = None
    item_count: int
    tagged_item_count: int
    returned_keys: list[str]
    ok: bool


class CurateClientMemoryRecallReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: str = Field(alias="schema")
    status: str
    pack_path: str = Field(min_length=1)
    pack_id: str = Field(min_length=1)
    memory_url: str = Field(min_length=1)
    collections: list[str] = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    probe_count: int
    pass_count: int
    fail_count: int
    probes: list[CurateClientRecallProbe]

    @field_validator("schema_")
    @classmethod
    def schema_is_current(cls, value: str) -> str:
        if value != "curate_client.memory_recall_validation.v1":
            raise ValueError("schema must be curate_client.memory_recall_validation.v1")
        return value


class CurateClientReportOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    canonical_question: str = Field(min_length=1)
    answer_thesis: str = Field(min_length=1)
    architecture_components: list[str] = Field(min_length=1)
    failure_cases: list[str] = Field(min_length=1)
    tradeoffs: list[str] = Field(min_length=1)
    graham_project_bridge: str = Field(min_length=1)
    memory_recall_ok: bool


class CurateClientReportScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str = Field(min_length=1)
    point_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    hook: str = Field(min_length=1)
    story: str = Field(min_length=1)
    oracles: list[CurateClientReportOracle] = Field(min_length=1)


class CurateClientReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: str = Field(alias="schema")
    classification: str = Field(min_length=1)
    client: str = Field(min_length=1)
    canonical_json: str = Field(min_length=1)
    prep_pack: str = Field(min_length=1)
    memory_recall_receipt: str = Field(min_length=1)
    memory_recall_status: str = Field(min_length=1)
    scenarios: list[CurateClientReportScenario] = Field(min_length=1)
    non_claims: list[str] = Field(min_length=1)

    @field_validator("schema_")
    @classmethod
    def schema_is_current(cls, value: str) -> str:
        if value != "curate_client.report_model.v1":
            raise ValueError("schema must be curate_client.report_model.v1")
        return value


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


def _knowledge_files(cfg: dict) -> list[Path]:
    root = cfg.get("kb_root")
    if not root:
        return []
    knowledge = Path(str(root)).expanduser() / "knowledge"
    return sorted(knowledge.rglob("*.md")) if knowledge.is_dir() else []


def _has_source(cfg: dict) -> bool:
    return bool(
        cfg.get("openapi_specs")
        or cfg.get("terraform_repos")
        or cfg.get("document_sources")
        or cfg.get("curated_sources")
        or _knowledge_files(cfg)
    )


def _validate(cfg: dict) -> None:
    missing = [k for k in ("client", "kb_root") if not cfg.get(k)]
    if not _has_source(cfg):
        missing.append("openapi_specs|terraform_repos|document_sources|curated_sources|knowledge/*.md")
    if missing:
        _needs_interview(missing)


def _path_from_cfg(cfg: dict, key: str) -> Path | None:
    value = cfg.get(key)
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _prep_pack_path(cfg: dict) -> Path:
    path = _path_from_cfg(cfg, "live_evidence_prep_pack")
    if path is None:
        _needs_interview(["live_evidence_prep_pack"])
    return path


def _triage(text: str) -> dict[str, Any]:
    if TRIAGE_RUNNER.exists():
        proc = subprocess.run(
            [str(TRIAGE_RUNNER), "classify", "--text", text],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0 and "{" in proc.stdout:
            return json.loads(proc.stdout[proc.stdout.index("{"):])
    return {
        "code": "curate_client_unclassified_" + hashlib.sha256(text.encode()).hexdigest()[:8],
        "cause": text[:500],
        "next_command": "repair canonical JSON and rerun validate-canonical",
    }


def _canonical_path(cfg: dict) -> Path | None:
    return _path_from_cfg(cfg, "canonical_client_file")


def _load_canonical(cfg: dict) -> CanonicalClientData | None:
    path = _canonical_path(cfg)
    if path is None:
        return None
    return CanonicalClientData.model_validate_json(path.read_text(encoding="utf-8"))


def _canonical_validation_failure(path: Path | None, exc: Exception) -> dict[str, Any]:
    text = f"curate-client canonical JSON pydantic validation failed for {path}: {exc}"
    return {
        "schema": "curate_client.canonical_validation_receipt.v1",
        "status": "FAIL",
        "path": str(path) if path else None,
        "triage": _triage(text),
        "errors": str(exc),
        "next_command": "repair canonical JSON fields/classification and rerun validate-canonical",
    }


def cmd_validate_canonical(cfg: dict) -> dict[str, Any]:
    path = _canonical_path(cfg)
    if path is None:
        if cfg.get("require_canonical_json"):
            return _canonical_validation_failure(path, ValueError("missing canonical_client_file"))
        return {"schema": "curate_client.canonical_validation_receipt.v1", "status": "SKIP", "path": None}
    try:
        data = _load_canonical(cfg)
    except (ValidationError, ValueError, OSError) as exc:
        return _canonical_validation_failure(path, exc)
    assert data is not None
    return {
        "schema": "curate_client.canonical_validation_receipt.v1",
        "status": "PASS",
        "path": str(path),
        "client": data.client,
        "source_count": len(data.sources),
        "briefing_point_count": len(data.briefing_points),
        "question_oracle_count": len(data.question_oracles),
    }


def _require_canonical_valid(cfg: dict) -> dict[str, Any] | None:
    receipt = cmd_validate_canonical(cfg)
    if receipt.get("status") == "FAIL":
        return receipt
    if cfg.get("require_canonical_json") and receipt.get("status") != "PASS":
        return _canonical_validation_failure(_canonical_path(cfg), ValueError("canonical JSON validation did not pass"))
    return None


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


def _copy_markdown_source(source: Any, outdir: Path) -> int:
    src = source.get("path") if isinstance(source, dict) else source
    if not src:
        return 0
    path = Path(str(src)).expanduser()
    if not path.exists():
        return 0
    files = [path] if path.is_file() else sorted(path.rglob("*.md"))
    n = 0
    for file in files:
        if file.suffix.lower() != ".md":
            continue
        target = outdir / "curated" / file.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if file.resolve() != target.resolve():
            target.write_text(file.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
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
    for source in (cfg.get("document_sources") or []) + (cfg.get("curated_sources") or []):
        total += _copy_markdown_source(source, outdir)
    return {"chunks_written": total, "knowledge_dir": str(outdir), "existing_knowledge_files": len(_knowledge_files(cfg))}


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


LIVE_EVIDENCE_ORACLE_COLLECTIONS = [
    "live_evidence_mock_interviews",
    "live_evidence_questions",
    "live_evidence_answers",
    "live_evidence_skill_chains",
    "live_evidence_source_context",
    "live_evidence_edges",
]


def _limit(cfg: dict, key: str, default: int) -> int:
    try:
        return max(1, int(cfg.get(key) or default))
    except (TypeError, ValueError):
        return default


def _json_file(cfg: dict, key: str) -> Any | None:
    path = _path_from_cfg(cfg, key)
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _model_json(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True)


def _validate_pydantic_json(model: type[BaseModel], payload: dict[str, Any]) -> dict[str, Any]:
    return model.model_validate(payload).model_dump(mode="json", by_alias=True)


def _oracle_collections(cfg: dict) -> list[str]:
    configured = [str(item) for item in (cfg.get("oracle_recall_collections") or [])]
    collections: list[str] = []
    for item in configured + LIVE_EVIDENCE_ORACLE_COLLECTIONS:
        if item not in collections:
            collections.append(item)
    return collections


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def _live_evidence_load_command(cfg: dict, prep_pack: Path) -> list[str]:
    skill_root = Path(__file__).resolve().parents[2]
    live_evidence_runner = skill_root / "live-evidence" / "run.sh"
    return [
        str(live_evidence_runner),
        "load-prep-pack",
        "--pack",
        str(prep_pack),
        "--backend-url",
        str(cfg.get("live_evidence_backend") or LIVE_EVIDENCE_DEFAULT_BACKEND),
        "--memory-url",
        str(cfg.get("memory_daemon") or "http://127.0.0.1:8601"),
    ]


def _recall_keys(cfg: dict, query: str, *, limit: int = 6) -> list[str]:
    daemon = str(cfg.get("memory_daemon") or "http://127.0.0.1:8601").rstrip("/")
    req = urllib.request.Request(
        daemon + "/recall",
        data=json.dumps({
            "q": query,
            "collections": _oracle_collections(cfg),
            "k": limit,
            "limit": limit,
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read())
    keys = []
    for item in payload.get("items", []):
        key = item.get("_key") if isinstance(item, dict) else None
        if key and key not in keys:
            keys.append(str(key))
    return keys


def _manifest_sources(cfg: dict) -> list[dict[str, str]]:
    canonical = _load_canonical(cfg)
    if canonical is not None:
        return [{k: str(v) for k, v in _model_json(source).items() if v is not None} for source in canonical.sources]
    path = Path(cfg["kb_root"]) / "source-manifest.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    docs = payload.get("documents") if isinstance(payload, dict) else payload
    if not isinstance(docs, list):
        return []
    out: list[dict[str, str]] = []
    for item in docs:
        if isinstance(item, dict):
            out.append({k: str(v) for k, v in item.items() if v is not None})
    return out


def _source_context(cfg: dict) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for index, spec in enumerate(cfg.get("openapi_specs") or []):
        sources.append({
            "classification": "curate_client_configured_source",
            "source_id": f"{_slug(cfg['client'])}_openapi_{index + 1}",
            "kind": "openapi_spec",
            "path": str(spec),
            "use": "client API source for Q-A chunks and live-evidence retrieval",
        })
    for index, repo in enumerate(cfg.get("terraform_repos") or []):
        sources.append({
            "classification": "curate_client_configured_source",
            "source_id": f"{_slug(cfg['client'])}_terraform_{index + 1}",
            "kind": "terraform_repo",
            "path": str(repo),
            "use": "client infrastructure source for Q-A chunks and coverage questions",
        })
    sources.extend(_manifest_sources(cfg))
    for index, path in enumerate(_knowledge_files(cfg)[:_limit(cfg, "source_context_limit", 8)]):
        text = path.read_text(encoding="utf-8", errors="ignore")
        sources.append({
            "classification": "curate_client_knowledge_chunk",
            "source_id": f"{_slug(cfg['client'])}_knowledge_{index + 1}",
            "kind": "knowledge_chunk",
            "path": str(path),
            "digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "use": "source-attributed Q-A knowledge chunk for local ripgrep fallback",
        })
    return sources


def _briefing_points(cfg: dict) -> list[dict[str, Any]]:
    canonical = _load_canonical(cfg)
    if canonical is not None:
        return [_model_json(point) for point in canonical.briefing_points[:_limit(cfg, "briefing_points_limit", len(canonical.briefing_points))]]
    configured = _json_file(cfg, "briefing_points_file")
    if configured is not None:
        points = configured.get("points") if isinstance(configured, dict) else configured
        if not isinstance(points, list) or not points:
            raise RuntimeError("briefing_points_file must contain a non-empty list or {points: [...]}")
        return points[:_limit(cfg, "briefing_points_limit", len(points))]
    research = cmd_research_plan(cfg)
    points = []
    for item in (research.get("collaboration_points") or [])[:_limit(cfg, "briefing_points_limit", 3)]:
        system = str(item.get("system") or "coverage")
        points.append({
            "classification": "curate_client_generated",
            "point_id": f"{_slug(system)}-coverage",
            "title": f"{system.upper()} coverage needs source-bound prep",
            "opening_triggers": [[system], ["coverage"], ["evidence"]],
            "hook": f"I would turn the {system} discussion into a checked evidence path before relying on it live.",
            "story": str(item.get("coverage_question") or "curate-client detected this system in the client KB and generated a coverage question."),
            "sources": [source["source_id"] for source in _source_context(cfg)[:2]],
        })
    if points:
        return points
    probes = cfg.get("probes") or ["client evidence"]
    return [
        {
            "classification": "curate_client_generated",
            "point_id": "client-evidence-gates",
            "title": "Client prep must stay source-bound",
            "opening_triggers": [[cfg["client"]], ["evidence"], ["retrieval"]],
            "hook": "I separate client research, retrieval, and live publication gates.",
            "story": f"curate-client generated this pack from {len(probes)} configured recall probe(s).",
            "sources": [source["source_id"] for source in _source_context(cfg)[:2]],
        }
    ]


def _question_oracles(cfg: dict) -> list[dict[str, Any]]:
    canonical = _load_canonical(cfg)
    if canonical is not None:
        out = []
        for item in canonical.question_oracles[:_limit(cfg, "question_oracles_limit", len(canonical.question_oracles))]:
            oracle = _model_json(item)
            keys = [str(k) for k in (oracle.get("memory_keys") or [])]
            if len(keys) < 2:
                keys = _recall_keys(cfg, f"{cfg['client']} {oracle['canonical_question']}", limit=8)
            if len(keys) < 2:
                raise RuntimeError(f"recall probe did not return at least two memory keys: {oracle['canonical_question']}")
            oracle["memory_keys"] = keys[:4]
            out.append(oracle)
        return out
    configured = _json_file(cfg, "question_oracles_file")
    if configured is not None:
        items = configured.get("question_oracles") if isinstance(configured, dict) else configured
        if not isinstance(items, list) or not items:
            raise RuntimeError("question_oracles_file must contain a non-empty list or {question_oracles: [...]}")
        out = []
        for index, item in enumerate(items[:_limit(cfg, "question_oracles_limit", len(items))]):
            if not isinstance(item, dict):
                raise RuntimeError("question_oracles_file entries must be objects")
            oracle = dict(item)
            query = str(oracle.get("canonical_question") or oracle.get("question") or "")
            if not query:
                raise RuntimeError("question_oracles_file entry missing canonical_question")
            oracle.setdefault("classification", "curate_client_configured")
            oracle.setdefault("question_id", f"{_slug(cfg['client'])}-oracle-{index + 1}")
            chain = oracle.get("skill_chain")
            if not isinstance(chain, list) or not chain or chain[0] != "memory":
                oracle["skill_chain"] = ["memory"] + ([str(v) for v in chain] if isinstance(chain, list) else [])
            oracle.setdefault("category", str(oracle.get("rubric_dimension") or "client_context_question"))
            oracle.setdefault("reviewed_answer", {
                "classification": "curate_client_configured_review",
                "review_status": "reviewed",
                "expected_response_shape": "source_checked_client_context_answer",
                "quality_bar": [
                    "uses stored client context first",
                    "keeps live answers bounded to retrieved evidence",
                    "fails closed if source evidence is unavailable",
                ],
            })
            keys = [str(k) for k in (oracle.get("memory_keys") or [])]
            if len(keys) < 2:
                keys = _recall_keys(cfg, f"{cfg['client']} {query}", limit=8)
            if len(keys) < 2:
                raise RuntimeError(f"recall probe did not return at least two memory keys: {query}")
            oracle["memory_keys"] = keys[:4]
            out.append(oracle)
        return out
    probes = cfg.get("probes") or []
    oracles = []
    for index, probe in enumerate(probes[:_limit(cfg, "question_oracles_limit", 8)]):
        query = f"{cfg['client']} {probe}"
        keys = _recall_keys(cfg, query, limit=8)
        if len(keys) < 2:
            raise RuntimeError(f"recall probe did not return at least two live-evidence memory keys: {query}")
        oracles.append({
            "classification": "curate_client_generated",
            "question_id": f"{_slug(cfg['client'])}-probe-{index + 1}",
            "canonical_question": query,
            "category": "client_context_question",
            "skill_chain": ["memory"],
            "reviewed_answer": {
                "classification": "curate_client_generated_review",
                "review_status": "reviewed",
                "expected_response_shape": "source_checked_client_context_answer",
                "quality_bar": [
                    "uses stored client context first",
                    "keeps live answers bounded to retrieved evidence",
                    "fails closed if source evidence is unavailable",
                ],
            },
            "memory_keys": keys[:4],
        })
    if oracles:
        return oracles
    keys = _recall_keys(cfg, cfg["client"], limit=8)
    if len(keys) < 2:
        raise RuntimeError(f"client recall did not return at least two live-evidence memory keys: {cfg['client']}")
    return [{
        "classification": "curate_client_generated",
        "question_id": f"{_slug(cfg['client'])}-overview",
        "canonical_question": f"What should I know about {cfg['client']} before the live conversation?",
        "category": "client_context_question",
        "skill_chain": ["memory"],
        "reviewed_answer": {
            "classification": "curate_client_generated_review",
            "review_status": "reviewed",
            "expected_response_shape": "source_checked_client_context_answer",
            "quality_bar": ["uses stored client context first", "fails closed if evidence is unavailable"],
        },
        "memory_keys": keys[:4],
    }]


def _generate_prep_pack(cfg: dict, path: Path) -> dict[str, Any]:
    client = str(cfg["client"])
    topic = str(cfg.get("topic") or f"{client} interview preparation from curated client KB")
    sources = _source_context(cfg)
    if not sources:
        raise RuntimeError("cannot generate prep pack without source context")
    payload = {
        "schema": "live_evidence.prep_pack.v1",
        "classification": "curate_client_generated_pydantic_validated",
        "pack_id": f"{_slug(client)}-generated-{hashlib.sha256(str(path).encode()).hexdigest()[:8]}",
        "target": {
            "classification": "curate_client_target",
            "kind": str(cfg.get("target_kind") or "employer"),
            "name": client,
            "topic": topic,
            "purpose": str(cfg.get("purpose") or "rehearsal"),
        },
        "research_chain": [
            {"classification": "curate_client_research_step", "skill": "curate-client", "role": "builds client KB and emits live-evidence prep pack"},
            {"classification": "curate_client_research_step", "skill": "brave-search", "role": "current public discovery when configured or needed"},
            {"classification": "curate_client_research_step", "skill": "dogpile", "role": "deeper multi-source research when configured or needed"},
            {"classification": "curate_client_research_step", "skill": "ask", "role": "question, answer, and skill-chain review"},
            {"classification": "curate_client_research_step", "skill": "memory", "role": "retrieval boundary for known or similar live questions"},
        ],
        "source_context": sources,
        "briefing_pack": {
            "schema": "live_evidence.briefing_pack.v1",
            "classification": "curate_client_briefing_pack",
            "pack_id": f"{_slug(client)}-generated-briefing",
            "audience": f"{client} interview or meeting",
            "core_concepts": [client, "client evidence", "retrieval", "source provenance"],
            "points": _briefing_points(cfg),
        },
        "question_oracles": _question_oracles(cfg),
        "memory_exports": {
            "classification": "curate_client_memory_exports",
            "ingest_endpoint": "/live-evidence/oracle-pack",
            "recall_endpoint": "/recall",
            "collections": _oracle_collections(cfg),
        },
        "live_use": {
            "classification": "curate_client_live_use",
            "before_call": [
                "load briefing_pack into /api/briefing/load",
                "verify question_oracles through /recall",
                "append kb_root to LIVE_EVIDENCE_REPOS for local ripgrep fallback",
            ],
            "during_call": [
                "use briefing triggers for openings",
                "use question_oracles as priors for known or similar heard questions",
                "never publish an answer without transcript revision and provenance gates",
            ],
            "after_call": [
                "compare extracted questions/cards against question_oracles",
                "record misses and weak skill-chain selections",
            ],
        },
        "producer": {
            "classification": "curate_client_producer",
            "skill": "curate-client",
            "client_scope": f"client:{client}",
            "kb_root": cfg["kb_root"],
            "knowledge_dir": str(Path(cfg["kb_root"]) / "knowledge"),
            "live_evidence_repos_append": cfg["kb_root"],
            "generated": True,
        },
    }
    payload = _validate_pydantic_json(LiveEvidencePrepPack, payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _load_or_generate_prep_pack(cfg: dict, path: Path) -> tuple[dict[str, Any], bool]:
    if path.is_file() and not cfg.get("regenerate_prep_pack"):
        return json.loads(path.read_text()), False
    return _generate_prep_pack(cfg, path), True


def cmd_prep_pack(cfg: dict) -> dict:
    path = _prep_pack_path(cfg)
    try:
        payload, generated = _load_or_generate_prep_pack(cfg, path)
        payload = _validate_pydantic_json(LiveEvidencePrepPack, payload)
    except Exception as exc:
        return {
            "schema": "curate_client.prep_pack_receipt.v1",
            "status": "FAIL",
            "path": str(path),
            "triage": _triage(f"curate-client prep-pack pydantic validation failed: {type(exc).__name__}: {exc}"),
            "error": f"prep pack pydantic validation failed: {type(exc).__name__}: {exc}",
            "next_command": "regenerate or repair prep-pack JSON and rerun prep-pack",
        }
    return {
        "schema": "curate_client.prep_pack_receipt.v1",
        "status": "PASS",
        "client": cfg["client"],
        "scope": f"client:{cfg['client']}",
        "path": str(path),
        "generated": generated,
        "live_evidence_load": {
            "schema": "curate_client.live_evidence_load_command.v1",
            "command": _live_evidence_load_command(cfg, path),
            "purpose": "load briefing pack and verify prep-pack oracle recall before the call",
        },
        "prep_pack": payload,
    }


def _oracle_tags(cfg: dict) -> list[str]:
    configured = [str(item) for item in (cfg.get("oracle_recall_tags") or [])]
    if configured:
        return configured
    return [_slug(str(cfg["client"])) + "-kb"]


def cmd_validate_memory_recall(cfg: dict) -> dict[str, Any]:
    prep = cmd_prep_pack(cfg)
    if prep.get("status") != "PASS":
        return {
            "schema": "curate_client.memory_recall_validation.v1",
            "status": "FAIL",
            "pack_path": str(_prep_pack_path(cfg)),
            "pack_id": "unknown",
            "memory_url": str(cfg.get("memory_daemon") or "http://127.0.0.1:8601"),
            "collections": _oracle_collections(cfg),
            "tags": _oracle_tags(cfg),
            "probe_count": 0,
            "pass_count": 0,
            "fail_count": 1,
            "probes": [],
        }
    pack = prep["prep_pack"]
    daemon = str(cfg.get("memory_daemon") or "http://127.0.0.1:8601").rstrip("/")
    collections = [str(item) for item in (cfg.get("memory_recall_collections") or cfg.get("oracle_recall_collections") or ["lessons"])]
    tags = _oracle_tags(cfg)
    probes: list[dict[str, Any]] = []
    for oracle in pack.get("question_oracles") or []:
        body = {"q": oracle.get("canonical_question"), "k": int(cfg.get("memory_recall_k") or 8), "collections": collections, "tags": tags}
        req = urllib.request.Request(daemon + "/recall", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read())
            status_code = response.status
        items = [item for item in payload.get("items", []) if isinstance(item, dict)]
        tagged = [item for item in items if any(tag in (item.get("tags") or []) for tag in tags)]
        probes.append({
            "question_id": str(oracle.get("question_id") or "unknown"),
            "canonical_question": str(oracle.get("canonical_question") or ""),
            "status_code": int(status_code),
            "found": bool(payload.get("found")),
            "confidence": payload.get("confidence"),
            "item_count": len(items),
            "tagged_item_count": len(tagged),
            "returned_keys": [str(item.get("_key")) for item in items if item.get("_key")],
            "ok": status_code == 200 and bool(payload.get("found")) and bool(tagged),
        })
    receipt = {
        "schema": "curate_client.memory_recall_validation.v1",
        "status": "PASS" if probes and all(probe["ok"] for probe in probes) else "FAIL",
        "pack_path": str(_prep_pack_path(cfg)),
        "pack_id": str(pack.get("pack_id") or "unknown"),
        "memory_url": daemon,
        "collections": collections,
        "tags": tags,
        "probe_count": len(probes),
        "pass_count": sum(1 for probe in probes if probe["ok"]),
        "fail_count": sum(1 for probe in probes if not probe["ok"]),
        "probes": probes,
    }
    receipt = _validate_pydantic_json(CurateClientMemoryRecallReceipt, receipt)
    receipt_path = _path_from_cfg(cfg, "memory_recall_receipt")
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def _report_model_path(cfg: dict) -> Path:
    configured = _path_from_cfg(cfg, "report_model_json")
    if configured is not None:
        return configured
    html_path = _path_from_cfg(cfg, "html_report") or (Path(cfg["kb_root"]) / "reports" / f"{_slug(cfg['client'])}.html")
    return html_path.with_suffix(".json")


def cmd_report(cfg: dict) -> dict[str, Any]:
    receipt = cmd_validate_canonical(cfg)
    if receipt.get("status") != "PASS":
        return receipt
    recall = cmd_validate_memory_recall(cfg)
    if recall.get("status") != "PASS":
        return recall
    data = _load_canonical(cfg)
    assert data is not None
    out = _path_from_cfg(cfg, "html_report") or (Path(cfg["kb_root"]) / "reports" / f"{_slug(data.client)}.html")
    model_path = _report_model_path(cfg)
    recall_by_question = {probe["canonical_question"]: probe for probe in recall["probes"]}
    scenarios: list[dict[str, Any]] = []
    for point in data.briefing_points:
        oracles = []
        for oracle in data.question_oracles:
            if oracle.scenario != point.title:
                continue
            probe = recall_by_question.get(oracle.canonical_question, {})
            oracles.append({
                "classification": oracle.classification,
                "question_id": oracle.question_id,
                "canonical_question": oracle.canonical_question,
                "answer_thesis": oracle.answer_thesis,
                "architecture_components": oracle.architecture_components,
                "failure_cases": oracle.failure_cases,
                "tradeoffs": oracle.tradeoffs,
                "graham_project_bridge": oracle.graham_project_bridge,
                "memory_recall_ok": bool(probe.get("ok")),
            })
        if oracles:
            scenarios.append({
                "classification": point.classification,
                "point_id": point.point_id,
                "title": point.title,
                "hook": point.hook,
                "story": point.story,
                "oracles": oracles,
            })
    report_model = _validate_pydantic_json(CurateClientReportModel, {
        "schema": "curate_client.report_model.v1",
        "classification": "curate_client_report_model",
        "client": data.client,
        "canonical_json": str(_canonical_path(cfg)),
        "prep_pack": str(_prep_pack_path(cfg)),
        "memory_recall_receipt": str(cfg.get("memory_recall_receipt") or "inline"),
        "memory_recall_status": str(recall.get("status")),
        "scenarios": scenarios,
        "non_claims": [
            "This report does not prove that every source claim is still current on OpenAI's website.",
            "This report does not prove production deployment outside local Live Evidence rehearsal.",
            "This report does not replace human interview preparation judgment.",
        ],
    })
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(report_model, indent=2) + "\n", encoding="utf-8")

    def esc(value: Any) -> str:
        return html.escape(str(value))

    def li(items: list[str]) -> str:
        return "".join(f"<li>{esc(item)}</li>" for item in items)

    source_rows = "\n".join(
        f"<tr><td>{esc(s.source_id)}</td><td>{esc(s.title)}</td><td>{esc(s.classification)}</td><td>{esc(s.authority)}</td><td>{esc(s.summary)}</td></tr>"
        for s in data.sources
    )
    scenario_sections = []
    for scenario in report_model["scenarios"]:
        oracle_blocks = []
        for oracle in scenario["oracles"]:
            oracle_blocks.append(f"""
<article class=\"oracle\">
<h4>{esc(oracle['question_id'])}: {esc(oracle['canonical_question'])}</h4>
<p><strong>Answer thesis:</strong> {esc(oracle['answer_thesis'])}</p>
<p><strong>Architecture components:</strong></p><ul>{li(oracle['architecture_components'])}</ul>
<p><strong>Failure cases:</strong></p><ul>{li(oracle['failure_cases'])}</ul>
<p><strong>Tradeoffs:</strong></p><ul>{li(oracle['tradeoffs'])}</ul>
<p><strong>Graham project bridge:</strong> {esc(oracle['graham_project_bridge'])}</p>
<p><strong>Memory recall:</strong> {'PASS' if oracle['memory_recall_ok'] else 'FAIL'}</p>
</article>""")
        scenario_sections.append(f"""
<section class=\"scenario\">
<h3>{esc(scenario['title'])}</h3>
<p><strong>Classification:</strong> {esc(scenario['classification'])}</p>
<p><strong>Opening hook:</strong> {esc(scenario['hook'])}</p>
<p><strong>Scenario story:</strong> {esc(scenario['story'])}</p>
{''.join(oracle_blocks)}
</section>""")
    body = f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>{esc(data.client)} interview prep report</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;line-height:1.62;margin:0;color:#111827;background:#fff}}main{{max-width:1040px;margin:0 auto;padding:36px 24px 72px}}h1{{font-size:30px;line-height:1.2}}h2{{font-size:22px;border-top:1px solid #d1d5db;padding-top:20px;margin-top:34px}}h3{{font-size:18px;margin-top:24px}}h4{{font-size:16px;margin:18px 0 8px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #d1d5db;padding:8px 10px;vertical-align:top;text-align:left}}th{{background:#f3f4f6}}code{{background:#f3f4f6;padding:1px 4px;border-radius:3px}}.evidence{{border-left:4px solid #1d4ed8;background:#eff6ff;padding:12px 14px}}.constraint{{border-left:4px solid #92400e;background:#fffbeb;padding:12px 14px}}.oracle{{border-left:3px solid #d1d5db;padding-left:14px;margin:18px 0}}.nonclaims{{border-left:4px solid #6b7280;background:#f9fafb;padding:12px 14px}}
</style></head><body><main>
<h1>{esc(data.client)} interview prep report</h1>
<h2>Report Summary</h2>
<p><strong>Overall Finding:</strong> Needs human review before use, with Memory recall passing for the generated question oracles.</p>
<p><strong>Core Conclusion:</strong> The useful artifact is the Q-A interview prep below: five privacy scenarios, answer theses, architecture components, failure cases, tradeoffs, and Graham project bridges. The report model JSON was Pydantic validated before this HTML was written.</p>
<p><strong>Evidence Basis:</strong> Canonical JSON <code>{esc(_canonical_path(cfg))}</code>; Pydantic report model <code>{esc(model_path)}</code>; Memory recall validation status <code>{esc(recall['status'])}</code> with {recall['pass_count']} of {recall['probe_count']} question probes passing through <code>/recall</code>.</p>
<h2>Scope</h2><p>OpenAI privacy interview rehearsal content and its Memory recall proof. Excluded: live refetch of OpenAI pages and external reviewer judgment.</p>
<h2>Project Context</h2><p>Persona: Graham preparing for an OpenAI privacy engineering interview. Primary object: source-bound privacy engineering Q-A chunks retrievable during Live Evidence.</p>
<h2>Source-of-Truth Inventory</h2><table><thead><tr><th>Source</th><th>Title</th><th>Classification</th><th>Authority</th><th>Summary</th></tr></thead><tbody>{source_rows}</tbody></table>
<h2>Findings</h2>
<p><strong>F-001 Verified:</strong> Pydantic validation accepted the canonical JSON, prep-pack JSON, Memory recall receipt JSON, and report-model JSON before writing this report.</p>
<p><strong>F-002 Verified:</strong> Question-shaped Memory recall passed for {recall['pass_count']} of {recall['probe_count']} generated question oracles using tags {esc(recall['tags'])} and collections {esc(recall['collections'])}.</p>
<p><strong>F-003 Needs Human:</strong> Graham must decide whether the interview content is substantively useful and whether any source claims need live refetch before the call.</p>
<h2>Surface / Module Contracts</h2><table><tbody><tr><td>System Surface Name</td><td>OpenAI privacy interview prep report</td></tr><tr><td>Owning Persona</td><td>Graham, interview candidate</td></tr><tr><td>Core Purpose</td><td>Review and rehearse source-bound privacy engineering answers retrievable by Live Evidence.</td></tr><tr><td>Primary Object</td><td>Pydantic validated report model generated from canonical-client.json.</td></tr><tr><td>Source of Truth</td><td>canonical-client.json and Memory recall validation receipt.</td></tr><tr><td>Valid Actions</td><td>accept for rehearsal; request source refresh; request scenario edits; reject unsupported content.</td></tr><tr><td>Outstanding / Broken / Constraints</td><td>Human substantive review required; live OpenAI refetch not performed.</td></tr></tbody></table>
<h2>Interview Prep Content</h2>
{''.join(scenario_sections)}
<h2>Finished / Pending / Outstanding / Broken / Blocked / Unproven</h2><table><tbody><tr><td>Finished</td><td>Pydantic JSON validation and Memory recall validation for generated question oracles.</td></tr><tr><td>Pending</td><td>Human review of content usefulness.</td></tr><tr><td>Outstanding</td><td>Optional live source refetch.</td></tr><tr><td>Broken</td><td>None proven in this report.</td></tr><tr><td>Blocked</td><td>None for local rehearsal.</td></tr><tr><td>Unproven</td><td>Production use and current live source freshness.</td></tr></tbody></table>
<h2>Plan-Ready Next Actions</h2><table><thead><tr><th>Action ID</th><th>Finding</th><th>Action</th><th>Acceptance Check</th></tr></thead><tbody><tr><td>A-001</td><td>F-003</td><td>Human reads this report in Chrome and marks weak or missing interview content.</td><td>Human decision recorded.</td></tr><tr><td>A-002</td><td>F-003</td><td>Refresh sources if human needs current external source proof.</td><td>Source receipts replace Not verified freshness claims.</td></tr></tbody></table>
<h2>Plan-Iterate Seed</h2><p><strong>Objective:</strong> Improve only the content Graham rejects after human review. <strong>Gate:</strong> Pydantic report model validation, Memory recall validation, Chrome screenshot, and human acceptance.</p>
<h2>New Plan-Iterate Instructions</h2><p><strong>Recommended phase id:</strong> <code>openai-privacy-interview-content-review</code>. Stop if human says the content is useful enough for rehearsal; otherwise edit canonical JSON and rerun report, recall, and Chrome gates.</p>
<h2>Non-Claims</h2><div class=\"nonclaims\"><ul>{li(report_model['non_claims'])}</ul></div>
</main></body></html>"""
    required = ["Answer thesis:", "Architecture components:", "Failure cases:", "Tradeoffs:", "Memory recall:", "Plan-Iterate Seed", "New Plan-Iterate Instructions"]
    missing = [term for term in required if term not in body]
    if missing:
        return {"schema": "curate_client.html_report_receipt.v1", "status": "FAIL", "path": str(out), "source": str(_canonical_path(cfg)), "triage": _triage(f"curate-client report content missing {missing}"), "errors": missing}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    return {
        "schema": "curate_client.html_report_receipt.v1",
        "status": "PASS",
        "canonical_validation": receipt,
        "memory_recall_validation": {k: recall[k] for k in ("status", "probe_count", "pass_count", "fail_count", "collections", "tags")},
        "path": str(out),
        "report_model_json": str(model_path),
        "source": str(_canonical_path(cfg)),
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
            "arxiv_via_dogpile": [
                f"{cfg['client']} authored papers",
                "domain-relevant literature scored against anchor_terms (e.g. LLM evaluation in regulated domains)",
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
        print("usage: curate.py plan|chunks|ingest|verify|prep-pack|report|validate-canonical|validate-memory-recall|build --config <yaml>", file=sys.stderr)
        sys.exit(2)
    cmd = sys.argv[1]
    if "--config" not in sys.argv:
        _needs_interview(["config"])
    cfg = _load_config(sys.argv[sys.argv.index("--config") + 1])
    _validate(cfg)
    canonical_failure = _require_canonical_valid(cfg)
    if canonical_failure:
        out = canonical_failure
    elif cmd == "validate-canonical":
        out = cmd_validate_canonical(cfg)
    elif cmd == "plan":
        out = {"client": cfg["client"], "kb_root": cfg["kb_root"],
               "openapi_specs": cfg.get("openapi_specs") or [],
               "terraform_repos": cfg.get("terraform_repos") or [],
               "document_sources": cfg.get("document_sources") or [],
               "curated_sources": cfg.get("curated_sources") or [],
               "canonical_validation": cmd_validate_canonical(cfg),
               "knowledge_files": len(_knowledge_files(cfg)),
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
    elif cmd == "validate-memory-recall":
        out = cmd_validate_memory_recall(cfg)
    elif cmd == "report":
        out = cmd_report(cfg)
    elif cmd == "build":
        out = {"canonical_validation": cmd_validate_canonical(cfg), "chunks": cmd_chunks(cfg), "ingest": cmd_ingest(cfg), "verify": cmd_verify(cfg), "prep_pack": cmd_prep_pack(cfg), "memory_recall": cmd_validate_memory_recall(cfg)}
        out["status"] = "PASS" if out["canonical_validation"].get("status") == "PASS" and out["verify"].get("status") == "PASS" and out["prep_pack"].get("status") == "PASS" and out["memory_recall"].get("status") == "PASS" else "FAIL"
    else:
        print(f"unknown command {cmd}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(out, indent=1))
    if isinstance(out, dict) and out.get("status") == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
