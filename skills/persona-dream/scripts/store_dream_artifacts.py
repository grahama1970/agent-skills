#!/usr/bin/env python3
"""Register a dream's media as memories, not just as files on disk.

A dream produces things she saw and heard: a contact sheet of the imagery, the
audio of her own voice reading the journal, and where a provider ran, rendered
video and frames. Left as files in a run directory those are build output. A
persona with no sensory autobiography has nothing to traverse -- she can recall
that she concluded something, but not the image it came from.

So each artifact becomes a memory carrying its modality, its path, its hash, and
a description in her own voice. The hash matters more than it looks: an artifact
memory that cannot be tied to the exact bytes it describes is a claim about a
picture nobody can produce.

Everything written here is SYNTHETIC and says so in the text as well as the
metadata. These are images from a dream. A retrieval path that drops the
metadata must still be unable to present them as photographs of things that
happened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
COLLECTION = "persona_memory"

#: What a dream can leave behind, and how she would refer to it.
ARTIFACTS = [
    ("contact_sheet.png", "image", "the imagery I saw in the dream, laid out as a contact sheet"),
    ("journal.wav", "audio", "my own voice reading the journal entry aloud"),
    ("provider_return.mp4", "video", "the dream rendered as moving image"),
]

#: Media is evocative but thin on its own; it should not outrank what was felt
#: or said. It is the thing a later dream reaches for when a tension recurs.
SALIENCE = 0.55


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def describe(run_dir: Path, name: str, modality: str, base: str) -> str:
    """Her description of the artifact, grounded in what the run recorded."""
    detail = ""
    if modality == "image":
        prompts = run_dir / "frame_prompts.json"
        if prompts.is_file():
            try:
                rows = json.loads(prompts.read_text(encoding="utf-8"))
                items = rows if isinstance(rows, list) else rows.get("frames") or []
                first = [str(r.get("prompt") or r.get("text") or "").strip() for r in items[:2]]
                first = [f for f in first if f]
                if first:
                    detail = " It showed: " + "; ".join(f[:120] for f in first)
            except (json.JSONDecodeError, AttributeError):
                pass
    elif modality == "audio":
        spoken = run_dir / "journal_spoken.txt"
        if spoken.is_file():
            text = " ".join(spoken.read_text(encoding="utf-8").split())
            if text:
                detail = f" I said: {text[:200]}"
    return f"From a dream: {base}.{detail}"


def reflection_key(run_dir: Path, persona: str, run_id: str) -> str | None:
    """The key of the dream reflection these artifacts belong to.

    Read from the run's own write receipt rather than recomputed. Recomputing
    the hash looked equivalent and was not: persona_dream hashes the reflection
    string it holds in memory, while dream_reflection.md on disk differs by
    formatting, so every artifact pointed at a key that did not exist and the
    traversal silently found nothing.

    Without a working edge the media are orphan nodes -- they appear in the
    multimodal graph but nothing reaches them, and walking from a memory to the
    imagery it produced is impossible.
    """
    receipt = run_dir / "memory_write_receipt.json"
    if not receipt.is_file():
        return None
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    # Only link to a reflection that actually landed. A key from a skipped or
    # errored write is a dangling edge dressed up as provenance.
    if data.get("status") != "ok" or not data.get("read_back"):
        return None
    return data.get("document_key")


def build_documents(run_dir: Path, persona: str, day: str, run_id: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    parent = reflection_key(run_dir, persona, run_id)
    for name, modality, base in ARTIFACTS:
        path = run_dir / name
        if not path.is_file():
            continue
        text = describe(run_dir, name, modality, base)
        digest = sha_file(path)
        docs.append({
            "_key": "pd_art_" + hashlib.sha256(f"{persona}:{digest}".encode()).hexdigest()[:24],
            "problem": f"A dream artifact {persona} produced on {day}",
            "solution": text,
            "scope": f"episodic:day={day}",
            "tags": ["persona-dream", "dream-artifact", f"modality:{modality}",
                     f"persona:{persona}", f"day:{day}"],
            "persona_id": persona,
            "record_type": "dream_artifact",
            "kind": "dream_artifact",
            "modality": modality,
            "synthetic": True,
            "synthetic_notice": (
                "an artifact of a synthetic dream, not a recording of anything that occurred"
            ),
            "artifact_path": rel(path),
            "artifact_sha256": digest,
            "artifact_bytes": path.stat().st_size,
            "salience": SALIENCE,
            "decay_class": "slow",
            "day": day,
            "dream_run_id": run_id,
            # The edge that makes this reachable. Traversal runs
            # memory -> reflection -> the imagery and audio it produced.
            "source_ids": [parent] if parent else [],
            "interprets_dream": parent,
        })
    return docs


def _client():
    import httpx
    return httpx.Client(transport=httpx.HTTPTransport(uds=MEMORY_SOCKET),
                        base_url="http://localhost", timeout=30.0)


def store(docs: list[dict[str, Any]], persona: str, day: str) -> tuple[list[dict[str, Any]], list[str]]:
    failed: list[str] = []
    results: list[dict[str, Any]] = []
    with _client() as client:
        for doc in docs:
            try:
                resp = client.post("/store", json={"document": doc, "collection": COLLECTION})
                status, err = resp.status_code, None
            except Exception as exc:  # noqa: BLE001
                status, err = 0, str(exc)
            if err or status >= 400:
                failed.append(f"store_failed:{doc['_key']}:{status}")
            results.append({"document_key": doc["_key"], "modality": doc["modality"],
                            "artifact": doc["artifact_path"], "store_http_status": status,
                            "store_error": err, "read_back": False})
        keys = {d["_key"] for d in docs}
        seen: set[str] = set()
        try:
            resp = client.post("/query", json={
                "aql": ("FOR d IN @@col FILTER d.day == @day AND d.record_type == 'dream_artifact' "
                        "AND d.persona_id == @p RETURN d._key"),
                "bind_vars": {"@col": COLLECTION, "day": day, "p": persona},
            })
            for raw in ((resp.json() or {}).get("documents") or []):
                key = raw if isinstance(raw, str) else str(raw.get("_key", ""))
                if key in keys:
                    seen.add(key)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"read_back_failed:{exc}")
    for r in results:
        r["read_back"] = r["document_key"] in seen
    missing = [r["document_key"] for r in results if not r["read_back"]]
    if missing:
        failed.append(f"stored_but_not_retrievable:{len(missing)}")
    return results, failed


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    packet = run_dir / "dream_packet.json"
    run_id = args.run_id or (json.loads(packet.read_text(encoding="utf-8")).get("run_id")
                             if packet.is_file() else run_dir.name)
    day = args.day or utc_now()[:10]

    docs = build_documents(run_dir, args.persona, day, str(run_id))
    if not docs:
        return {
            "schema": "persona_dream.dream_artifact_receipt.v1", "created_at": utc_now(),
            "status": "BLOCKED_NO_ARTIFACTS", "mocked": False, "live": False,
            "run_dir": rel(run_dir),
            "failed_gates": [f"no artifacts found in {rel(run_dir)}"],
        }

    results, failed = store(docs, args.persona, day)
    by_modality = sorted({d["modality"] for d in docs})

    return {
        "schema": "persona_dream.dream_artifact_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_DREAM_ARTIFACTS_STORED" if not failed else "BLOCKED_DREAM_ARTIFACTS",
        "mocked": False,
        "live": True,
        "run_dir": rel(run_dir),
        "persona": args.persona,
        "day": day,
        "scope": f"episodic:day={day}",
        "collection": COLLECTION,
        "modalities": by_modality,
        "artifacts": results,
        "read_back_count": sum(1 for r in results if r["read_back"]),
        "synthetic_rule": (
            "every artifact memory is marked synthetic in metadata AND prefixed 'From a "
            "dream:' in its text, so a retrieval path that drops the metadata still cannot "
            "present dream imagery as a recording of something that happened"
        ),
        "hash_rule": (
            "each artifact memory carries the sha256 of the exact bytes it describes; an "
            "artifact memory that cannot be tied to its file is a claim about a picture "
            "nobody can produce"
        ),
        "claims": {
            "proves": [
                "the dream's media are retrievable as memories, by modality and by day",
                "each is bound by hash to the file it describes",
            ] if not failed else [],
            "does_not_prove": [
                "that the media improve a later dream",
                "anything about the visual or audio quality of the artifacts",
            ],
        },
        "failed_gates": failed,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--persona", default="embry")
    ap.add_argument("--day", help="YYYY-MM-DD; defaults to today")
    ap.add_argument("--run-id")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = run(args)
    if args.out:
        Path(args.out).write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(r, indent=2, sort_keys=True) if args.json else
          f"{r['status']}  modalities={r.get('modalities')}  read_back={r.get('read_back_count')}"
          + (f"  failed={r['failed_gates']}" if r.get("failed_gates") else ""))
    return 0 if r["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
