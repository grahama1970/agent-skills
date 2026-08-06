"""io - pitchdeck.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class SkillError(RuntimeError):
    """Expected user-correctable failure with a precise remediation message."""


def expand_path(value: str, *, base_dir: Path | None = None) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(value))
    path = Path(expanded)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


def load_yaml(path: Path, model: type[T]) -> T:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillError(f"Missing YAML file: {path}") from exc
    except yaml.YAMLError as exc:
        raise SkillError(f"Invalid YAML in {path}: {exc}") from exc
    try:
        return model.model_validate(raw)
    except Exception as exc:
        raise SkillError(f"Schema validation failed for {path}: {exc}") from exc


def dump_yaml(model: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json", exclude_none=True, by_alias=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def dump_json(model: BaseModel | dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json", exclude_none=True, by_alias=True) if isinstance(model, BaseModel) else model
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str, *, fallback: str = "item") -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return value or fallback


def copy_tree_contents(source: Path, destination: Path, *, force: bool = False) -> None:
    if not source.exists():
        raise SkillError(f"Scaffold profile does not exist: {source}")
    if destination.exists() and any(destination.iterdir()) and not force:
        raise SkillError(
            f"Destination is not empty: {destination}. Use --force to merge/overwrite files."
        )
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=force)
        else:
            if target.exists() and not force:
                raise SkillError(f"Refusing to overwrite {target}; use --force")
            shutil.copy2(item, target)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
