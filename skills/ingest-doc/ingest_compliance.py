#!/usr/bin/env python3
"""Ingest Compliance Document — end-to-end pipeline for defense/compliance PDFs."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

app = typer.Typer(help="End-to-end compliance document ingestion pipeline")

SKILLS_DIR = Path(__file__).parent.parent
EXTRACTOR = SKILLS_DIR / "extractor" / "run.sh"
CUI_MARKER = SKILLS_DIR / "cui-marker" / "run.sh"
# Removed: memory accessed via httpx to Unix socket

# HTTP service endpoints (no subprocess for these services)
_CHUTES_CALL_URL = os.environ.get("CHUTES_CALL_URL", "http://localhost:8630")
_MEMORY_SOCKET = f"/run/user/{os.getuid()}/embry/memory.sock"
_MEMORY_HTTP = os.environ.get("MEMORY_SERVICE_URL", "http://127.0.0.1:8601")


def _memory_client() -> httpx.Client:
    """Get httpx client for memory daemon (Unix socket preferred, HTTP fallback)."""
    socket = Path(_MEMORY_SOCKET)
    if socket.exists():
        transport = httpx.HTTPTransport(uds=str(socket))
        return httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)
    return httpx.Client(base_url=_MEMORY_HTTP, timeout=30.0)


def _run_doc2qra_http(file_path: str, scope: str) -> tuple[bool, str]:
    """Extract QRAs via chutes-call /batch HTTP service (port 8630)."""
    try:
        text = Path(file_path).read_text()[:3000]
    except Exception as e:
        return False, f"Cannot read file: {e}"

    payload = {
        "requests": [{
            "messages": [
                {"role": "system", "content": (
                    "You are a knowledge extraction assistant. Respond with valid JSON only. "
                    'Return {"items": [{"question": "string", "reasoning": "string", "answer": "string"}, ...]}'
                )},
                {"role": "user", "content": f"Extract all grounded knowledge items from this text.\n\nText:\n{text}\n\nJSON:"},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "temperature": 0.1,
        }],
        "concurrency": 1,
        "tenacious": True,
        "caller": "ingest-doc",
    }
    try:
        resp = httpx.post(f"{_CHUTES_CALL_URL}/batch", json=payload, timeout=120.0)
        if resp.status_code == 200:
            results = resp.json()
            if results and isinstance(results, list) and results[0].get("ok"):
                return True, json.dumps(results[0])
        return False, f"chutes-call returned status {resp.status_code}"
    except Exception as e:
        return False, f"chutes-call /batch error: {e}"


def _run_taxonomy_http(file_path: str) -> tuple[bool, str]:
    """Extract taxonomy tags via memory daemon /taxonomy/tag endpoint."""
    try:
        text = Path(file_path).read_text()[:3000]
    except Exception as e:
        return False, f"Cannot read file: {e}"

    try:
        client = _memory_client()
        resp = client.post("/taxonomy/tag", json={"text": text, "fast": True})
        client.close()
        if resp.status_code == 200:
            return True, resp.text
        return False, f"Taxonomy returned status {resp.status_code}"
    except Exception as e:
        return False, f"Taxonomy error: {e}"


def _skill_available(skill_path: Path) -> bool:
    return skill_path.exists() and skill_path.is_file()


def _run_skill(skill_path: Path, args: list[str], label: str) -> tuple[bool, str]:
    """Run a skill and return (success, output)."""
    if not _skill_available(skill_path):
        return False, f"Skill not found: {skill_path}"

    try:
        result = subprocess.run(
            ["bash", str(skill_path)] + args,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "PYTHONPATH": f"{SKILLS_DIR}:{os.environ.get('PYTHONPATH', '')}"},
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return False, f"{label} failed (exit {result.returncode}): {output[:500]}"
        return True, output
    except subprocess.TimeoutExpired:
        return False, f"{label} timed out after 600s"
    except Exception as e:
        return False, f"{label} error: {e}"


@app.command()
def ingest(
    path: str = typer.Argument(..., help="PDF path or URL to ingest"),
    preset: Optional[str] = typer.Option(None, help="Force extractor preset"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing"),
    skip_cui: bool = typer.Option(False, "--skip-cui", help="Skip CUI marking (public docs)"),
    scope: str = typer.Option("compliance", help="Memory scope for storage"),
):
    """Run the full compliance ingestion pipeline."""
    doc_path = Path(path) if not path.startswith("http") else None
    if doc_path and not doc_path.exists():
        typer.echo(f"File not found: {path}")
        raise typer.Exit(1)

    stages = [
        ("extractor", "Extract document content"),
        ("cui-marker", "Scan for CUI indicators") if not skip_cui else None,
        ("doc2qra", "Extract QRA pairs"),
        ("taxonomy", "Extract taxonomy tags"),
        ("memory", "Store to memory"),
    ]
    stages = [s for s in stages if s is not None]

    if dry_run:
        typer.echo("=== Dry Run — Compliance Ingestion Pipeline ===\n")
        typer.echo(f"Document: {path}")
        typer.echo(f"Preset: {preset or 'auto-detect'}")
        typer.echo(f"Scope: {scope}")
        typer.echo(f"CUI check: {'skip' if skip_cui else 'enabled'}\n")
        for i, (skill, desc) in enumerate(stages, 1):
            available = _skill_available(SKILLS_DIR / skill / "run.sh")
            status = "ready" if available else "MISSING"
            typer.echo(f"  [{i}/{len(stages)}] {desc} ({skill}) — {status}")
        return

    typer.echo(f"=== Compliance Ingestion: {path} ===\n")
    monitor = TaskClient("ingest-doc", total=len(stages)) if TaskClient else None

    # Stage 1: Extract
    typer.echo(f"[1/{len(stages)}] Extracting document content...")
    extract_args = [path]
    if preset:
        extract_args.extend(["--preset", preset])
    ok, output = _run_skill(EXTRACTOR, extract_args, "Extractor")
    if not ok:
        typer.echo(f"  FAILED: {output}")
        raise typer.Exit(1)
    typer.echo(f"  Done. {len(output)} chars extracted")

    # Stage 2: CUI check (optional)
    stage_idx = 2
    if not skip_cui:
        typer.echo(f"[{stage_idx}/{len(stages)}] Scanning for CUI indicators...")
        ok, output = _run_skill(CUI_MARKER, ["scan", path], "CUI Marker")
        if ok:
            try:
                cui_result = json.loads(output)
                if cui_result.get("cui_detected"):
                    cats = ", ".join(cui_result.get("categories", []))
                    typer.echo(f"  CUI detected: {cats}")
                    typer.echo(f"  Marking: {cui_result.get('recommended_marking', 'N/A')}")
                else:
                    typer.echo("  No CUI indicators found")
            except json.JSONDecodeError:
                typer.echo("  CUI scan completed (non-JSON output)")
        else:
            typer.echo(f"  Warning: CUI scan failed: {output[:200]}")
        stage_idx += 1

    # Stage 3: Extract QRA pairs via chutes-call /batch HTTP service
    typer.echo(f"[{stage_idx}/{len(stages)}] Extracting QRA pairs via chutes-call /batch...")
    ok, output = _run_doc2qra_http(path, scope)
    if ok:
        typer.echo(f"  QRA pairs extracted")
    else:
        typer.echo(f"  Warning: QRA extraction failed: {output[:200]}")
    stage_idx += 1

    # Stage 4: Taxonomy via memory daemon /taxonomy/tag endpoint
    typer.echo(f"[{stage_idx}/{len(stages)}] Extracting taxonomy tags...")
    ok, output = _run_taxonomy_http(path)
    if ok:
        typer.echo(f"  Taxonomy tags extracted")
    else:
        typer.echo(f"  Warning: Taxonomy extraction failed: {output[:200]}")
    stage_idx += 1

    # Stage 5: Memory storage via daemon HTTP
    typer.echo(f"[{stage_idx}/{len(stages)}] Storing to memory (scope: {scope})...")
    try:
        client = _memory_client()
        resp = client.post("/learn", json={
            "problem": f"Compliance document: {Path(path).name}",
            "solution": f"Ingested via pipeline, scope={scope}",
            "scope": scope,
        })
        client.close()
        if resp.status_code == 200:
            typer.echo(f"  Stored to memory")
        else:
            typer.echo(f"  Warning: Memory storage returned status {resp.status_code}")
    except Exception as e:
        typer.echo(f"  Warning: Memory storage failed: {str(e)[:200]}")

    if monitor:
        monitor.finish()
    typer.echo(f"\nDone. Pipeline complete for: {path}")


@app.command()
def batch(
    directory: Path = typer.Argument(..., help="Directory of documents to process"),
    preset: Optional[str] = typer.Option(None, help="Force extractor preset"),
    skip_cui: bool = typer.Option(False, "--skip-cui"),
    scope: str = typer.Option("compliance"),
    format: Optional[str] = typer.Option(None, "--format", help="Filter by extension (e.g. html, pdf). Default: all supported."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search subdirectories"),
):
    """Process all supported documents in a directory."""
    if not directory.is_dir():
        typer.echo(f"Not a directory: {directory}")
        raise typer.Exit(1)

    supported_exts = {"*.pdf", "*.html", "*.htm", "*.docx", "*.md", "*.xml"}
    glob_fn = directory.rglob if recursive else directory.glob

    if format:
        pattern = f"*.{format.lstrip('.')}"
        docs = sorted(glob_fn(pattern))
    else:
        docs = sorted(f for ext in supported_exts for f in glob_fn(ext))

    if not docs:
        typer.echo(f"No supported documents found in {directory}")
        raise typer.Exit(1)

    typer.echo(f"Found {len(docs)} documents in {directory}\n")
    batch_monitor = TaskClient("ingest-doc-batch", total=len(docs)) if TaskClient else None
    for i, doc in enumerate(docs, 1):
        typer.echo(f"\n{'='*60}")
        typer.echo(f"[{i}/{len(docs)}] {doc.name}")
        typer.echo(f"{'='*60}")
        try:
            ingest(str(doc), preset=preset, dry_run=False, skip_cui=skip_cui, scope=scope)
        except SystemExit:
            typer.echo(f"  FAILED — continuing with next document")
        if batch_monitor:
            batch_monitor.update(item=doc.name)

    if batch_monitor:
        batch_monitor.finish()
    typer.echo(f"\nBatch complete: {len(docs)} documents processed")


@app.command()
def status():
    """Check pipeline health — are all required skills available?"""
    skills = {
        "extractor": EXTRACTOR,
        "cui-marker": CUI_MARKER,
    }

    typer.echo("=== Compliance Ingestion Pipeline Status ===\n")
    all_ok = True
    for name, path in skills.items():
        available = _skill_available(path)
        status = "ready" if available else "MISSING"
        icon = "ok" if available else "FAIL"
        typer.echo(f"  [{icon}] {name:25s} {path}")
        if not available:
            all_ok = False

    typer.echo()
    if all_ok:
        typer.echo("Pipeline ready — all skills available")
    else:
        typer.echo("Pipeline NOT ready — missing skills detected")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
