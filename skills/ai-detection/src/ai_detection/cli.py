"""Thin Typer entrypoints for serving, research, independent verification, and skill delegation."""
import dataclasses
import importlib.util
import os
import shutil
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from dotenv import load_dotenv
from loguru import logger
from pydantic import ValidationError

from ai_detection.analysis import analyze
from ai_detection.api import create_app, home_path, load_policy
from ai_detection.contracts import EvidenceExport, Policy
from ai_detection.dataset import audit_splits, load_records
from ai_detection.errors import Code, DetectionError, envelope
from ai_detection.humanize import Transform, humanize, probe_fragility
from ai_detection.io import atomic_json, canonical, read_json
from ai_detection.jev_shadow import run_shadow
from ai_detection.model import evaluate, load_model, model_digest, save_model, train
from ai_detection.native import invoke_native
from ai_detection.provenance import CommitSignal, classify, detector_label, survey
from ai_detection.verify import verify_export

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")



load_dotenv(override=False)
def emit(value) -> None:
    typer.echo(canonical(value).decode("utf-8"))


def fail(exc: Exception) -> None:
    logger.error("operation_failed exception_type={}", type(exc).__name__)
    if isinstance(exc, DetectionError):
        emit(envelope(exc).model_dump(mode="json"))
    elif isinstance(exc, ValidationError):
        result = envelope(DetectionError(Code.INVALID_INPUT, "Typed validation failed.")).model_dump()
        result["validation_errors"] = [{"type": item["type"], "loc": list(item["loc"]),
                                       "msg": "Field failed typed validation.", "ctx": {}}
                                      for item in exc.errors()]
        emit(result)
    else:
        emit(envelope(DetectionError(Code.INVALID_INPUT, "Input could not be processed.")).model_dump())
    raise typer.Exit(3)

@app.command()
def doctor() -> None:
    """Report capabilities and missing proof without claiming native skills were executed."""
    native = os.environ.get("AGENT_SKILLS_ROOT")
    emit({"schema_version": "ai_detection.doctor.v1", "software": "0.1.0",
          "home": str(home_path()), "default_model": "NONE_ABSTAIN",
          "chromium": shutil.which("chromium") or shutil.which("google-chrome"),
          "optional_transformers": importlib.util.find_spec("transformers") is not None,
          "native_skills_present": bool(native and (Path(native) / "skills/agentic-evals/run.sh").is_file()),
          "real_world_detection": "NOT_ESTABLISHED", "public_deployment": "NOT_ESTABLISHED"})

@config_app.command("doctor")
def config_doctor() -> None:
    doctor()

@config_app.command("init")
def config_init(output: Path = Path("policy.local.json")) -> None:
    if output.exists():
        fail(DetectionError(Code.CONFLICT, "Refusing to replace an existing policy file."))
    atomic_json(output, Policy().model_dump(mode="json"))
    emit({"created": str(output)})

@app.command()
def serve(port: Annotated[int, typer.Option(min=1024, max=65535)] = 8765,
          container_network: bool = False) -> None:
    """Serve on loopback. Container binding is explicit and still uses the local-research trust model."""
    try:
        application = create_app()
    except (DetectionError, ValidationError, OSError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)
        return
    uvicorn.run(application, host="0.0.0.0" if container_network else "127.0.0.1", port=port,
                access_log=False, proxy_headers=False)

@app.command("analyze")
def analyze_command(source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
                    language: str = "python", model: Path | None = None,
                    policy: Path | None = None, output: Path | None = None) -> None:
    try:
        if source.stat().st_size > 512000:
            raise DetectionError(Code.LIMIT, "Source exceeds the file byte limit.")
        result = analyze(source.read_text(encoding="utf-8"), language, load_policy(policy),
                         load_model(model) if model else None)
        if output:
            atomic_json(output, result.model_dump(mode="json"))
        emit(result.model_dump(mode="json"))
    except (DetectionError, ValidationError, OSError, UnicodeError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("humanize")
def humanize_command(source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
                     transform: Transform = Transform.AST_REFORMAT,
                     code: bool = False, output: Path | None = None) -> None:
    """Red-team style-normalization probe. Default: fragility receipt over all
    transforms. --code emits the humanized source for the chosen --transform.
    Mechanism-only: feature movement here is detector fragility, not evasion."""
    try:
        if source.stat().st_size > 512000:
            raise DetectionError(Code.LIMIT, "Source exceeds the file byte limit.")
        text = source.read_text(encoding="utf-8")
        if code:
            typer.echo(humanize(text, transform))
            return
        result = {"schema": "ai_detection.fragility_probe.v1", "feature_version": "python-multiview-1",
                  "claim": "detector feature-view movement under style normalization",
                  "does_not_prove": "evasion, authorship, or detection efficacy",
                  "fragility": [dataclasses.asdict(f) for f in probe_fragility(text)]}
        if output:
            atomic_json(output, result)
        emit(result)
    except (DetectionError, ValidationError, OSError, UnicodeError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)


@app.command("classify-provenance")
def classify_provenance(metadata: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Classify commit METADATA (JSON list of {author_login, message}) into the
    three provenance tiers. Metadata only, no code content -> no licensing risk.
    Emits per-commit class + label and a survey count for corpus planning."""
    try:
        rows = read_json(metadata)
        if not isinstance(rows, list):
            raise DetectionError(Code.INVALID_INPUT, "Expect a JSON list of commit metadata objects.")
        signals = [CommitSignal(author_login=str(r.get("author_login", "")),
                                message=str(r.get("message", ""))) for r in rows]
        items = [{"provenance": classify(s).value, "label": detector_label(classify(s))} for s in signals]
        emit({"schema": "ai_detection.provenance_survey.v1",
              "does_not_prove": "authorship, efficacy, or that any class may feed the strong-label tier",
              "counts": survey(signals), "items": items})
    except (DetectionError, ValidationError, OSError, UnicodeError, ValueError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)


@app.command("jev-shadow")
def jev_shadow_command(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option()],
    allow_provider_upload: bool = False,
) -> None:
    """Run pinned Jev as an advisory shadow; never changes detector/Battle decisions."""
    try:
        root = Path(os.environ.get("AGENT_SKILLS_ROOT", Path(__file__).resolve().parents[4]))
        receipt = run_shadow(source, output, allow_provider_upload=allow_provider_upload,
                             agent_skills_root=root)
        emit(receipt.model_dump(mode="json", by_alias=True))
        if receipt.outcome != "accepted":
            raise typer.Exit(3)
    except (OSError, ValidationError, ValueError) as exc:
        logger.error("classified_failure module=jev_shadow")
        fail(exc)


@app.command("train")
def train_command(corpus: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
                  output: Path, report: Path, allow_synthetic: bool = False,
                  policy: Path | None = None) -> None:
    try:
        selected = load_policy(policy)
        model, benchmark = train(load_records(corpus, allow_synthetic), selected.target_fpr,
                                 selected.confidence)
        save_model(output, model)
        atomic_json(report, benchmark)
        emit({"model": str(output), "model_sha256": model_digest(model),
              "benchmark": str(report), "deployment_readiness": "NOT_ESTABLISHED"})
    except (DetectionError, ValidationError, OSError, ValueError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("audit-dataset")
def audit_dataset(corpus: Path, allow_synthetic: bool = False) -> None:
    try:
        emit(audit_splits(load_records(corpus, allow_synthetic)))
    except (DetectionError, ValidationError, OSError, ValueError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("benchmark")
def benchmark(corpus: Path, model: Path, output: Path, allow_synthetic: bool = False) -> None:
    try:
        result = evaluate(load_model(model), load_records(corpus, allow_synthetic))
        atomic_json(output, result)
        emit(result)
    except (DetectionError, ValidationError, OSError, ValueError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("verify-evidence")
def verify_evidence(path: Path, output: Path | None = None) -> None:
    try:
        report = verify_export(EvidenceExport.model_validate(read_json(path, 32_000_000)))
        if output:
            atomic_json(output, report)
        emit(report)
    except (DetectionError, ValidationError, OSError, ValueError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("reference-manifest")
def reference_manifest(path: Path) -> None:
    from ai_detection.research import weights_manifest
    try:
        emit({"manifest_sha256": weights_manifest(path)})
    except (DetectionError, OSError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("reference-score")
def reference_score(request: Path, output: Path) -> None:
    from ai_detection.research import ReferenceRequest, local_reference_score
    try:
        result = local_reference_score(ReferenceRequest.model_validate(read_json(request)))
        atomic_json(output, result.model_dump(mode="json"))
        emit(result.model_dump(mode="json"))
    except (DetectionError, ValidationError, OSError, ValueError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("native-evals")
def native_evals(project: Path = Path.cwd(), output: Path = Path("reports/native-evals.json"),
                 release: bool = False) -> None:
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        raise typer.Exit(invoke_native("agentic-evals", project.resolve(), output,
                                      "release" if release else "mechanisms"))
    except (DetectionError, OSError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("native-setup")
def native_setup(project: Path = Path.cwd(), output: Path = Path("reports/native-setup.json"),
                 plan: bool = False) -> None:
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        raise typer.Exit(invoke_native("setup-project", project.resolve(), output,
                                      "plan" if plan else "audit"))
    except (DetectionError, OSError) as exc:
        logger.error("classified_failure module=cli")
        fail(exc)

@app.command("efficacy-gate")
def efficacy_gate(request: Path, output: Path, policy: Path | None = None) -> None:
    """Recompute frozen-corpus numeric acceptance; never replace human provenance review."""
    from ai_detection.efficacy import EfficacyRequest, qualify
    try:
        result = qualify(EfficacyRequest.model_validate(read_json(request)), load_policy(policy))
        atomic_json(output, result.model_dump(mode="json"))
        emit(result.model_dump(mode="json"))
        if result.status != "PASS":
            raise typer.Exit(3)
    except (DetectionError, ValidationError, OSError, ValueError) as exc:
        fail(exc)


@app.command("release-gate")
def release_gate(output: Path = Path("reports/release-gate.json")) -> None:
    """Execute both owning gates. No constant PASS, and no local imitation of native readiness."""
    results = {}
    for skill, mode in (("setup-project", "audit"), ("agentic-evals", "release")):
        destination = output.parent / f"{skill}-release.json"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            code = invoke_native(skill, Path.cwd().resolve(), destination, mode)
            results[skill] = {"executed": True, "exit_code": code, "receipt": str(destination)}
        except (DetectionError, OSError):
            logger.error("native_release_gate_blocked skill={}", skill)
            results[skill] = {"executed": False, "exit_code": 3, "receipt": str(destination)}
    passed = all(item["executed"] and item["exit_code"] == 0 for item in results.values())
    result = {"schema_version": "ai_detection.release_invocation.v1", "native_gates_passed": passed,
              "readiness": "NATIVE_GATES_PASSED_REVIEW_RECEIPTS" if passed else "NOT_ESTABLISHED",
              "owning_gate_results": results, "automatic_penalties": False,
              "note": "Read the owning claim-level reports; this invocation summary is not authorship evidence."}
    atomic_json(output, result)
    emit(result)
    raise typer.Exit(0 if passed else 3)
