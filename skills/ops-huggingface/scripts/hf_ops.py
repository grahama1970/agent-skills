#!/usr/bin/env python3
"""Dry-run-first Hugging Face Hub operations CLI.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(hf_ops.cpython-312.pyc) after the .py source was lost — it was never tracked
in git and no source copy survived on disk or in any branch. Reconstruction is
faithful to the 3.12 disassembly of every function (pycdc could recover the
plain helpers but not the typer-decorated commands, which were rebuilt from
their bytecode op-by-op). Behaviour matches the deployed bytecode; this file is
now TRACKED so the skill cannot be lost again.

Operate Hugging Face Hub repos, uploads, snapshots, and cards with dry-run
safety defaults: mutation commands (create-repo, upload, snapshot) only touch
the Hub when --execute is passed, and every receipt records an auth check
without exposing token values.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import typer

app = typer.Typer(
    add_completion=False,
    help="Operate Hugging Face Hub repos, uploads, snapshots, and cards with dry-run safety defaults.",
)


def load_dotenv() -> None:
    """Load simple KEY=VALUE entries from the repository .env if present."""
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")


def load_hf():
    """Import huggingface_hub lazily, failing with a clear CLI error if absent."""
    try:
        from huggingface_hub import (
            HfApi,
            create_repo,
            snapshot_download,
            upload_file,
            upload_folder,
        )

        return (HfApi, create_repo, snapshot_download, upload_file, upload_folder)
    except Exception as exc:
        raise typer.BadParameter(
            "Missing dependency: huggingface_hub. Install it in the active "
            "environment or run from a project environment that already provides it."
        ) from exc


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


def token_available() -> bool:
    return bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))


def auth_receipt(*, check_remote: bool) -> dict[str, Any]:
    """Return auth state without exposing token values.

    Dry-run mutation receipts need to prove an auth check happened without
    requiring a Hub network call. `huggingface_hub.get_token()` detects cached
    CLI tokens as well as env tokens.
    """
    env_token = token_available()
    cached_token = False
    if not env_token:
        from huggingface_hub import get_token

        cached_token = bool(get_token())
    receipt: dict[str, Any] = {
        "auth_checked": True,
        "token_available": env_token or cached_token,
        "auth_source": "env" if env_token else ("huggingface_hub_cache" if cached_token else "none"),
    }
    if check_remote:
        try:
            HfApi, *_ = load_hf()
            info = HfApi().whoami()
            receipt.update({
                "authenticated": True,
                "name": info.get("name"),
                "orgs": [o.get("name") for o in info.get("orgs", [])],
            })
        except Exception as exc:
            receipt.update({"authenticated": False, "error": str(exc)})
    return receipt


def public_item(item: Any) -> dict[str, Any]:
    keys = ("id", "modelId", "author", "likes", "downloads", "tags", "pipeline_tag", "lastModified")
    out: dict[str, Any] = {}
    for key in keys:
        value = getattr(item, key, None)
        if value is not None:
            out[key] = value
    return out


@app.command()
def whoami(json_output: bool = typer.Option(True, "--json/--no-json")) -> None:
    """Check Hugging Face authentication without exposing token values."""
    payload = {"command": "whoami", **auth_receipt(check_remote=True)}
    emit(payload, json_output)


@app.command("search-models")
def search_models(
    query: str,
    limit: int = 20,
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Search Hub model repositories."""
    HfApi, *_ = load_hf()
    results = list(HfApi().list_models(search=query, limit=limit))
    emit({
        "command": "search-models",
        "query": query,
        "limit": limit,
        "count": len(results),
        "results": [public_item(item) for item in results],
    }, json_output)


@app.command("search-datasets")
def search_datasets(
    query: str,
    limit: int = 20,
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Search Hub dataset repositories."""
    HfApi, *_ = load_hf()
    results = list(HfApi().list_datasets(search=query, limit=limit))
    emit({
        "command": "search-datasets",
        "query": query,
        "limit": limit,
        "count": len(results),
        "results": [public_item(item) for item in results],
    }, json_output)


@app.command("repo-info")
def repo_info(
    repo: str,
    repo_type: str = typer.Option("model", "--type", case_sensitive=False),
    files_metadata: bool = False,
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Inspect an existing Hub repository."""
    HfApi, *_ = load_hf()
    auth = auth_receipt(check_remote=False)
    try:
        info = HfApi().repo_info(repo, repo_type=repo_type, files_metadata=files_metadata)
        emit({
            "command": "repo-info",
            "repo_id": repo,
            "repo_type": repo_type,
            "found": True,
            "sha": getattr(info, "sha", None),
            "private": getattr(info, "private", None),
            "last_modified": getattr(info, "lastModified", None),
            "siblings": [getattr(s, "rfilename", None) for s in getattr(info, "siblings", [])],
            **auth,
        }, json_output)
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        state = "absent_or_inaccessible" if status_code in {401, 403, 404} or status_code is None else "error"
        emit({
            "command": "repo-info",
            "repo_id": repo,
            "repo_type": repo_type,
            "found": False,
            "state": state,
            "http_status": status_code,
            "error_type": type(exc).__name__,
            "error": str(exc),
            **auth,
        }, json_output)


@app.command("list-files")
def list_files(
    repo: str,
    repo_type: str = typer.Option("model", "--type", case_sensitive=False),
    revision: Optional[str] = None,
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """List files in a Hub repository."""
    HfApi, *_ = load_hf()
    files = list(HfApi().list_repo_files(repo, repo_type=repo_type, revision=revision))
    emit({
        "command": "list-files",
        "repo_id": repo,
        "repo_type": repo_type,
        "revision": revision,
        "count": len(files),
        "files": files,
    }, json_output)


@app.command("create-repo")
def create_repo_cmd(
    repo: str,
    repo_type: str = typer.Option("model", "--type", case_sensitive=False),
    public: bool = typer.Option(False, "--public/--private", help="Create a public repo. Default is private."),
    exist_ok: bool = False,
    execute: bool = False,
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Create a Hub repository; dry-run unless --execute is present."""
    payload = {
        "command": "create-repo",
        "repo_id": repo,
        "repo_type": repo_type,
        "private": not public,
        "dry_run": not execute,
        "executed": False,
        **auth_receipt(check_remote=False),
    }
    if execute:
        _, create_repo, *_ = load_hf()
        result = create_repo(repo_id=repo, repo_type=repo_type, private=not public, exist_ok=exist_ok)
        payload.update({"executed": True, "url": str(result)})
    emit(payload, json_output)


@app.command()
def upload(
    path: Path,
    repo: str = typer.Option(..., "--repo"),
    repo_type: str = typer.Option("model", "--type", case_sensitive=False),
    path_in_repo: Optional[str] = None,
    message: str = "Upload via ops-huggingface",
    execute: bool = False,
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Upload a file or folder to a Hub repository; dry-run unless --execute is present."""
    source = path.expanduser().resolve()
    if not source.exists():
        raise typer.BadParameter(f"Upload source does not exist: {source}")
    payload = {
        "command": "upload",
        "repo_id": repo,
        "repo_type": repo_type,
        "source": str(source),
        "path_in_repo": path_in_repo,
        "commit_message": message,
        "dry_run": not execute,
        "executed": False,
        **auth_receipt(check_remote=False),
        "is_dir": source.is_dir(),
    }
    if execute:
        _, _, _, upload_file, upload_folder = load_hf()
        if source.is_dir():
            result = upload_folder(
                folder_path=str(source),
                repo_id=repo,
                repo_type=repo_type,
                path_in_repo=path_in_repo,
                commit_message=message,
            )
        else:
            result = upload_file(
                path_or_fileobj=str(source),
                path_in_repo=path_in_repo or source.name,
                repo_id=repo,
                repo_type=repo_type,
                commit_message=message,
            )
        payload.update({"executed": True, "url": str(result)})
    emit(payload, json_output)


@app.command()
def snapshot(
    repo: str,
    local_dir: Path = typer.Option(..., "--local-dir"),
    repo_type: str = typer.Option("model", "--type", case_sensitive=False),
    revision: Optional[str] = None,
    execute: bool = False,
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Download a repository snapshot; dry-run unless --execute is present."""
    payload = {
        "command": "snapshot",
        "repo_id": repo,
        "repo_type": repo_type,
        "local_dir": str(local_dir),
        "revision": revision,
        "dry_run": not execute,
        "executed": False,
        **auth_receipt(check_remote=False),
    }
    if execute:
        _, _, snapshot_download, *_ = load_hf()
        path = snapshot_download(repo_id=repo, repo_type=repo_type, revision=revision, local_dir=str(local_dir))
        payload.update({"executed": True, "snapshot_path": path})
    emit(payload, json_output)


def validate_card_text(text: str, repo_type: str) -> tuple[bool, list[str]]:
    lower = text.lower()
    missing: list[str] = []
    if not text.lstrip().startswith("---"):
        missing.append("yaml_frontmatter")
    for field in ("license", "tags", "intended use", "limitations"):
        if field not in lower:
            missing.append(field.replace(" ", "_"))
    if repo_type == "model":
        for field in ("model details", "evaluation", "training"):
            if field not in lower:
                missing.append(field.replace(" ", "_"))
    if repo_type == "dataset":
        for field in ("dataset description", "data fields", "source"):
            if field not in lower:
                missing.append(field.replace(" ", "_"))
    return (not missing, missing)


@app.command("validate-card")
def validate_card(
    path: Path,
    repo_type: str = typer.Option("model", "--type", case_sensitive=False),
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Validate a model/dataset card for required sections."""
    card = path.expanduser().resolve()
    if not card.exists():
        raise typer.BadParameter(f"Card file does not exist: {card}")
    ok, missing = validate_card_text(card.read_text(encoding="utf-8"), repo_type)
    emit({
        "command": "validate-card",
        "repo_type": repo_type,
        "path": str(card),
        "valid": ok,
        "missing": missing,
        "card_validated": True,
    }, json_output)


@app.command("template-card")
def template_card(
    repo_type: str = typer.Option(..., "--type", case_sensitive=False),
    repo: str = typer.Option(..., "--repo"),
    output: Path = typer.Option(..., "--output"),
    name: Optional[str] = None,
    license_name: str = typer.Option("TODO", "--license"),
    overwrite: bool = False,
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Write a starter model/dataset card with required sections stubbed."""
    title = name if name else repo
    if repo_type == "model":
        body = (
            f"---\nlicense: {license_name}\ntags:\n  - TODO\n---\n\n# {title}\n\n"
            "## Model Details\n\nTODO: Fill from verified training and promotion artifacts.\n\n"
            "## Intended Use\n\nTODO: State intended use and out-of-scope use.\n\n"
            "## Training\n\nTODO: Name data source, split policy, and training configuration.\n\n"
            "## Evaluation\n\nTODO: Report held-out metrics and benchmark artifacts.\n\n"
            "## Limitations\n\nTODO: State known limitations and failure modes.\n"
        )
    else:
        body = (
            f"---\nlicense: {license_name}\ntags:\n  - TODO\n---\n\n# {title}\n\n"
            "## Dataset Description\n\nTODO: Fill from verified dataset artifacts.\n\n"
            "## Source\n\nTODO: Name provenance, collection method, and consent/licensing constraints.\n\n"
            "## Data Fields\n\nTODO: Describe fields and schemas.\n\n"
            "## Intended Use\n\nTODO: State intended use and out-of-scope use.\n\n"
            "## Limitations\n\nTODO: State known limitations, biases, and quality issues.\n"
        )
    out = output.expanduser().resolve()
    if out.exists() and not overwrite:
        raise typer.BadParameter(f"Refusing to overwrite existing card without --overwrite: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    ok, missing = validate_card_text(body, repo_type)
    emit({
        "command": "template-card",
        "repo_id": repo,
        "repo_type": repo_type,
        "output": str(out),
        "valid": ok,
        "missing": missing,
    }, json_output)


if __name__ == "__main__":
    load_dotenv()
    app()
