"""Compose MIDI arrangement via LLM using /prompt-lab prompt.

Reads annotated lyrics + MIDI fragments + arrangement notes + heart tags,
calls the scillm proxy with the midi_arrangement_v1 prompt (managed by /prompt-lab),
and writes piano-roll-spec.json.

Prompt location: .pi/skills/prompt-lab/prompts/midi_arrangement_v1.txt
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx
import typer
from loguru import logger

app = typer.Typer(
    name="compose",
    help="Compose a MIDI arrangement via LLM using /prompt-lab midi_arrangement_v1 prompt.",
)

# Prompt managed by /prompt-lab — lives in prompt-lab's versioned prompts directory
_PROMPT_NAME = "midi_arrangement_v1"
_PROMPT_LAB_DIR = Path(__file__).parent.parent / "prompt-lab" / "prompts"

# Required piano-roll-spec.json top-level keys
_REQUIRED_SPEC_KEYS = {"bpm", "time_signature", "key", "total_bars", "sections", "notes"}


def _load_prompt(name: str) -> str:
    """Load a versioned prompt template from /prompt-lab/prompts/."""
    path = _PROMPT_LAB_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt '{name}' not found in /prompt-lab prompts: {path}\n"
            f"Add the prompt file to .pi/skills/prompt-lab/prompts/{name}.txt"
        )
    return path.read_text()


def _build_user_message(
    lyrics_data: dict,
    refs_data: dict,
    heart_tags: list[str],
    arrangement_text: str,
) -> str:
    """Build the structured user message for the LLM arrangement call."""
    parts = [
        "## Annotated Lyrics (from /create-lyrics)",
        "```json",
        json.dumps(lyrics_data, indent=2),
        "```",
        "",
        "## MIDI Reference Fragments (from /consume-midi)",
        "```json",
        json.dumps(refs_data, indent=2),
        "```",
        "",
        "## Heart Tags (emotional arc per section)",
        ", ".join(heart_tags),
        "",
    ]

    if arrangement_text.strip():
        parts += [
            "## Arrangement Notes",
            arrangement_text.strip(),
            "",
        ]

    parts.append(
        "Compose the full multi-track piano-roll-spec.json now. "
        "Return ONLY valid JSON — no markdown, no explanation."
    )
    return "\n".join(parts)


def _validate_spec(spec: dict) -> list[str]:
    """Return list of missing required keys in piano-roll-spec."""
    return sorted(_REQUIRED_SPEC_KEYS - set(spec.keys()))


async def _call_scillm(system: str, user: str, model: Optional[str]) -> dict:
    """POST to scillm proxy (prompt-lab infrastructure) and return parsed JSON spec."""
    api_base = os.environ.get("SCILLM_API_BASE", "http://localhost:4001/v1").strip("\"'")
    api_key = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123").strip("\"'")

    # Model resolution: CLI flag > env vars > sensible default
    model_id = (
        model
        or os.environ.get("CHUTES_MODEL_ID", "").strip("\"'")
        or os.environ.get("CHUTES_TEXT_MODEL", "").strip("\"'")
        or "deepseek-ai/DeepSeek-V3-0324"
    )

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 8192,
        "temperature": 0.3,
    }

    logger.info("LLM call: model={} endpoint={}", model_id, api_base)
    t0 = time.perf_counter()

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()

    latency_ms = (time.perf_counter() - t0) * 1000
    data = resp.json()

    raw = data["choices"][0]["message"]["content"]
    logger.info("LLM responded in {:.0f}ms ({} chars)", latency_ms, len(raw))

    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


@app.command()
def compose(
    lyrics: str = typer.Option(..., "--lyrics", help="Path to annotated-lyrics.json"),
    references: str = typer.Option(..., "--references", help="Path to consume-midi fragments JSON"),
    heart: str = typer.Option(
        ..., "--heart", help="Comma-separated heart tags (e.g. anger,sadness,fear)"
    ),
    out: str = typer.Option(..., "--out", help="Output piano-roll-spec.json path"),
    arrangement: Optional[str] = typer.Option(
        None, "--arrangement", help="Path to arrangement notes (.md or .txt)"
    ),
    model: Optional[str] = typer.Option(None, "--model", help="Override LLM model ID"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print prompt without calling LLM (for debugging)"
    ),
) -> None:
    """Compose a MIDI arrangement via LLM.

    Reads annotated lyrics + MIDI reference fragments + heart tags, calls the
    scillm proxy with the /prompt-lab midi_arrangement_v1 prompt, and writes
    piano-roll-spec.json matching the schema expected by midi_utils from-spec.
    """
    # --- Load inputs ---
    lyrics_path = Path(lyrics)
    if not lyrics_path.exists():
        logger.error("Lyrics file not found: {}", lyrics_path)
        raise typer.Exit(1)

    refs_path = Path(references)
    if not refs_path.exists():
        logger.error("References file not found: {}", refs_path)
        raise typer.Exit(1)

    lyrics_data: dict = json.loads(lyrics_path.read_text())
    refs_data: dict = json.loads(refs_path.read_text())

    arrangement_text = ""
    if arrangement:
        arr_path = Path(arrangement)
        if arr_path.exists():
            arrangement_text = arr_path.read_text()
        else:
            logger.warning("Arrangement notes not found (skipping): {}", arr_path)

    heart_tags = [t.strip() for t in heart.split(",") if t.strip()]
    if not heart_tags:
        logger.error("--heart must contain at least one tag")
        raise typer.Exit(1)
    logger.info("Heart tags: {}", heart_tags)

    # --- Load system prompt from /prompt-lab ---
    try:
        system_prompt = _load_prompt(_PROMPT_NAME)
    except FileNotFoundError as exc:
        logger.error("{}", exc)
        raise typer.Exit(1)

    user_msg = _build_user_message(
        lyrics_data=lyrics_data,
        refs_data=refs_data,
        heart_tags=heart_tags,
        arrangement_text=arrangement_text,
    )

    # --- Dry-run: show prompt and exit ---
    if dry_run:
        logger.info("=== SYSTEM PROMPT ({} chars) ===\n{}", len(system_prompt), system_prompt)
        logger.info("=== USER MESSAGE ({} chars) ===\n{}", len(user_msg), user_msg)
        logger.info("Dry-run complete — no LLM call made")
        return

    # --- Call scillm proxy (prompt-lab infrastructure) ---
    try:
        spec = asyncio.run(_call_scillm(system_prompt, user_msg, model))
    except httpx.HTTPStatusError as exc:
        logger.error("LLM HTTP error {}: {}", exc.response.status_code, exc.response.text)
        raise typer.Exit(1)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned non-JSON response: {}", exc)
        raise typer.Exit(1)
    except Exception as exc:
        logger.error("LLM call failed: {}", exc)
        raise typer.Exit(1)

    # --- Validate spec ---
    missing = _validate_spec(spec)
    if missing:
        logger.warning("piano-roll-spec missing keys: {} — output may be incomplete", missing)

    note_count = len(spec.get("notes", []))
    logger.info(
        "Arrangement: {} bars, {} sections, {} notes, {} BPM",
        spec.get("total_bars", "?"),
        len(spec.get("sections", [])),
        note_count,
        spec.get("bpm", "?"),
    )

    # --- Write output ---
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spec, indent=2))
    logger.info("Wrote piano-roll-spec: {}", out_path)


if __name__ == "__main__":
    app()
