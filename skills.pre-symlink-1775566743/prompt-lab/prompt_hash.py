"""Prompt hash verification for /prompt-lab.

Prevents bespoke prompts by embedding a salted hash in prompt files.
The hash covers the prompt content + a project-level salt that agents
cannot access or forge.

Usage:
    # Seal a prompt after /prompt-lab eval passes
    python prompt_hash.py seal prompts/my_prompt.txt

    # Verify a prompt file has a valid hash
    python prompt_hash.py verify prompts/my_prompt.txt

    # Verify all prompts in a directory
    python prompt_hash.py verify-all prompts/

Format in prompt file (first 2 lines):
    # prompt-lab-hash: sha256:<hex-digest>
    # prompt-lab-eval: <iso-timestamp> score=<float> model=<model>
    <actual prompt content>
"""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

# Salt lives at .pi/prompt-lab-salt (two levels up from this file in .pi/skills/prompt-lab/)
SALT_FILE = Path(__file__).resolve().parent.parent.parent / "prompt-lab-salt"
HASH_PREFIX = "# prompt-lab-hash: sha256:"
EVAL_PREFIX = "# prompt-lab-eval: "


def _load_salt() -> str:
    if not SALT_FILE.exists():
        logger.error("No prompt-lab-salt file at {}", SALT_FILE)
        raise FileNotFoundError(f"Missing {SALT_FILE} — run: python -c 'import secrets; print(secrets.token_hex(16))' > {SALT_FILE}")
    return SALT_FILE.read_text().strip()


def compute_hash(content: str) -> str:
    """Compute salted SHA256 hash of prompt content."""
    salt = _load_salt()
    payload = salt + "\n" + content
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seal_prompt(path: Path, score: float = 0.0, model: str = "unknown") -> str:
    """Add hash header to a prompt file. Returns the hash."""
    text = path.read_text(encoding="utf-8")

    # Strip existing headers if re-sealing
    lines = text.splitlines()
    content_lines = []
    for line in lines:
        if line.startswith(HASH_PREFIX) or line.startswith(EVAL_PREFIX):
            continue
        content_lines.append(line)

    content = "\n".join(content_lines).strip()
    digest = compute_hash(content)
    timestamp = datetime.now(timezone.utc).isoformat()

    header = f"{HASH_PREFIX}{digest}\n{EVAL_PREFIX}{timestamp} score={score} model={model}\n"
    path.write_text(header + content + "\n", encoding="utf-8")

    return digest


def verify_prompt(path: Path) -> tuple[bool, str]:
    """Verify a prompt file's hash. Returns (valid, reason)."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not lines or not lines[0].startswith(HASH_PREFIX):
        return False, "no prompt-lab-hash header — prompt was not sealed by /prompt-lab"

    stored_hash = lines[0][len(HASH_PREFIX):].strip()

    # Extract content (everything after header lines)
    content_lines = []
    for line in lines:
        if line.startswith(HASH_PREFIX) or line.startswith(EVAL_PREFIX):
            continue
        content_lines.append(line)

    content = "\n".join(content_lines).strip()
    computed = compute_hash(content)

    if computed != stored_hash:
        return False, f"hash mismatch — prompt was modified after sealing (stored={stored_hash[:12]}... computed={computed[:12]}...)"

    # Extract eval metadata
    eval_line = lines[1] if len(lines) > 1 and lines[1].startswith(EVAL_PREFIX) else ""
    return True, f"valid ({eval_line[len(EVAL_PREFIX):].strip() if eval_line else 'no eval metadata'})"


def verify_directory(directory: Path) -> list[dict]:
    """Verify all .txt prompt files in a directory."""
    results = []
    for txt in sorted(directory.glob("*.txt")):
        valid, reason = verify_prompt(txt)
        results.append({"file": txt.name, "valid": valid, "reason": reason})
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="Prompt hash verification for /prompt-lab.")


@app.command()
def seal(
    path: Path = typer.Argument(..., help="Prompt file to seal"),
    score: float = typer.Option(0.0, help="Eval score from /prompt-lab"),
    model: str = typer.Option("unknown", help="Model used for eval"),
) -> None:
    """Seal a prompt file with a salted hash after eval passes."""
    if not path.exists():
        logger.error("File not found: {}", path)
        raise typer.Exit(1)

    digest = seal_prompt(path, score, model)
    logger.info("Sealed {} with hash {}", path.name, digest[:16])


@app.command()
def verify(
    path: Path = typer.Argument(..., help="Prompt file or directory to verify"),
) -> None:
    """Verify prompt file(s) have valid hashes."""
    if path.is_dir():
        results = verify_directory(path)
        failed = [r for r in results if not r["valid"]]
        for r in results:
            status = "PASS" if r["valid"] else "FAIL"
            print(f"  {status}: {r['file']} — {r['reason']}")
        if failed:
            print(f"\n{len(failed)} prompt(s) FAILED verification")
            raise typer.Exit(1)
        else:
            print(f"\nAll {len(results)} prompt(s) verified")
    else:
        valid, reason = verify_prompt(path)
        print(f"{'PASS' if valid else 'FAIL'}: {path.name} — {reason}")
        if not valid:
            raise typer.Exit(1)


if __name__ == "__main__":
    app()
