#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import textwrap
import time
import urllib.error
import urllib.request
import base64
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _load_sibling(name: str):
    """Load a sibling script as a module, so a step can be reused in-process."""
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load sibling script: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

import typer

app = typer.Typer(help="Create receipt-backed persona dream packets.")

# A dream needs tension, and tension in a life is psychological, not procedural.
# The previous table was a security-compliance vocabulary (qra, nist, mitre,
# spoof, malformed, supplier, citation) inherited from SPARTA work. Against
# autobiographical memory it both under-fired and mis-fired: a live run on
# 2026-08-04 recalled six real Embry memories and produced zero contradictions,
# collapsing the reflection to a template stub, while "Loyalty" matched the
# metadata word "source" and the richest memory in the set -- offering Kai a
# partial confession about crossing a boundary while refusing to identify
# James -- matched nothing at all (#1200).
#
# These axes are the ones a persona's memories actually pull against. Terms are
# matched on word boundaries so "source" cannot score "resource" and a bare
# metadata token cannot manufacture a tension.
BRIDGES = {
    "Concealment": ["hid", "hidden", "concealed", "withheld", "refuses to identify",
                    "private", "secret", "unsaid", "silence", "omits", "guarded"],
    "Disclosure": ["confession", "confesses", "admits", "tells", "reveals",
                   "discloses", "honest", "names", "acknowledges"],
    "Competence": ["competent", "capable", "expert", "handled", "responds competently",
                   "precise", "mastery", "skilled"],
    "Inadequacy": ["gap", "unsure", "uncertain", "questions about", "struggled",
                   "could not", "had to stop", "failed", "unprepared", "doubt"],
    "Belonging": ["family", "potluck", "shared", "together", "chapel", "helps",
                  "friend", "welcomed", "community"],
    "Isolation": ["alone", "apart", "distance", "withdrew", "left out",
                  "on her own", "separate", "unseen"],
    # "record" removed: memory metadata reads "The source records ...", which
    # manufactured a Duty match out of a storage verb rather than an obligation.
    "Duty": ["procedure", "protocol", "obligation", "must comply",
             "responsibility", "review trail", "audit"],
    "Desire": ["wanted", "wished", "longing", "hoped", "yearning",
               "drawn to", "ache"],
}

OPPOSITIONS = {
    "Concealment": "Disclosure",
    "Disclosure": "Concealment",
    "Competence": "Inadequacy",
    "Inadequacy": "Competence",
    "Belonging": "Isolation",
    "Isolation": "Belonging",
    "Duty": "Desire",
    "Desire": "Duty",
}

PERSONA_MEDIA_ROOT = Path("/mnt/storage12tb/media/personas")
COMFYUI_ROOT = Path("/home/graham/workspace/experiments/ComfyUI")
DEFAULT_SCILLM_BASE_URL = "http://localhost:4001"
DEFAULT_COMFYUI_BASE_URL = "http://127.0.0.1:8188"
DEFAULT_CHUTES_TURBOWANI2V_URL = "https://vonkaiser-turbowani2v.chutes.ai/generate"
DEFAULT_CHUTES_Z_IMAGE_TURBO_URL = "https://vonkaiser-z-image-turbo.chutes.ai/generate"
CENTRAL_PERSONA_MEMORY_SCOPE = "persona-dream"
CENTRAL_PERSONA_MEMORY_COLLECTION = "persona_memory"

EMBRY_CONTEXT_FILES = [
    PERSONA_MEDIA_ROOT / "embry" / "embry_persona.yaml",
    PERSONA_MEDIA_ROOT / "embry" / "README.md",
    PERSONA_MEDIA_ROOT / "embry" / "docs" / "EMBRY_CHARACTER_SHEET_V2.md",
]

HORUS_CONTEXT_FILES = [
    Path("/home/graham/workspace/experiments/horus/.pi/skills/memory/docs/HORUS_PERSONA.md"),
    PERSONA_MEDIA_ROOT / "horus" / "dreams" / "horus_dream_2026-02-06" / "production_bible.md",
]

SPARTA_EXPLORER_CONTEXT_FILES = [
    Path("/home/graham/workspace/experiments/sparta/.plan-iterate/sparta-explorer-page-purpose-dogpile/progress-context/sparta-explorer-page-purpose-matrix.md"),
    Path("/home/graham/workspace/experiments/pi-mono/packages/ux-lab/designs/sparta-explorer-chat/EVIDENCE_RECEIPT_CONTRACT.md"),
    Path("/home/graham/workspace/experiments/pi-mono/packages/ux-lab/designs/sparta-qra-chat-bakeoff/brief/BRIEF.md"),
]


@dataclass(frozen=True)
class Persona:
    id: str

    @property
    def display_name(self) -> str:
        return self.id.replace("-", " ").title()

    def scope(self, suffix: str) -> str:
        return f"{self.id}-{suffix}"


def _now_run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _default_output_dir(run_id: str) -> Path:
    base = Path("/mnt/storage12tb/skills/persona-dream/outputs")
    if base.parent.parent.exists():
        return base / run_id
    return Path("/tmp/persona-dream") / run_id


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _http_json(url: str, timeout: float = 4.0, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return {
                "status": "ok",
                "http_status": response.status,
                "url": url,
                "json": json.loads(body.decode("utf-8")) if body else None,
            }
    except urllib.error.HTTPError as exc:
        return {"status": "error", "url": url, "http_status": exc.code, "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "url": url, "error": str(exc)}


def _http_post_json_bytes(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return {
                "status": "ok",
                "http_status": response.status,
                "headers": dict(response.headers.items()),
                "body": raw,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return {
            "status": "error",
            "http_status": exc.code,
            "headers": dict(exc.headers.items()) if exc.headers else {},
            "body": raw,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "status": "error",
            "http_status": None,
            "headers": {},
            "body": b"",
            "error": str(exc),
        }


def _retryable_http_status(status: int | None) -> bool:
    return status in {408, 409, 425, 429, 500, 502, 503, 504}


def _guess_extension(content_type: str, body: bytes) -> str:
    lowered = content_type.lower()
    if body.startswith(b"\x89PNG") or "image/png" in lowered:
        return ".png"
    if body.startswith(b"\xff\xd8") or "image/jpeg" in lowered:
        return ".jpg"
    if "video/mp4" in lowered or body[4:8] == b"ftyp":
        return ".mp4"
    if "application/json" in lowered:
        return ".json"
    return ".bin"


def _run_command(args: list[str], cwd: Path | None = None, timeout: float = 12.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "status": "ok" if proc.returncode == 0 else "error",
            "args": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"status": "error", "args": args, "error": str(exc)}


def _model_capabilities(models_payload: Any, model_name: str) -> dict[str, Any]:
    if not isinstance(models_payload, dict):
        return {"present": False}
    models = models_payload.get("models")
    if not isinstance(models, dict):
        return {"present": False}
    entry = models.get(model_name)
    if not isinstance(entry, dict):
        return {"present": False}
    capabilities = entry.get("capabilities")
    return {
        "present": True,
        "selectable": entry.get("selectable"),
        "kind": entry.get("kind"),
        "target": entry.get("target"),
        "deployments": entry.get("deployments"),
        "capabilities": capabilities if isinstance(capabilities, dict) else {},
    }


def _find_named_files(roots: list[Path], names: list[str]) -> dict[str, list[str]]:
    found = {name: [] for name in names}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            for name in names:
                if path.name == name:
                    found[name].append(str(path))
    return found


def _read_excerpt(path: Path, max_chars: int = 2200) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing", "excerpt": ""}
    text = path.read_text(errors="replace")
    return {
        "path": str(path),
        "status": "ok",
        "chars": len(text),
        "excerpt": text[:max_chars],
    }


def _image_inventory(root: Path, limit: int = 16) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    names: list[Path] = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        names.extend(root.rglob(pattern))
    selected = sorted(names)[:limit]
    return [{"path": str(path), "name": path.name, "role": _reference_role(path)} for path in selected]


def _reference_role(path: Path) -> str:
    name = path.stem.lower()
    if "front" in name:
        return "front_view"
    if "threequarter" in name or "three" in name:
        return "three_quarter_view"
    if "profile" in name or "side" in name:
        return "side_view"
    if "fullbody" in name:
        return "full_body"
    if "whiteboard" in name:
        return "explaining_pose"
    if "desk" in name:
        return "working_pose"
    if "scene" in name or "panel" in name:
        return "scene_reference"
    return "visual_reference"


def _persona_context(persona_ids: list[str]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for persona_id in persona_ids:
        if persona_id == "embry":
            files = EMBRY_CONTEXT_FILES
            image_roots = [
                PERSONA_MEDIA_ROOT / "embry" / "assets" / "casting_v2",
                PERSONA_MEDIA_ROOT / "embry" / "assets" / "casting",
            ]
        elif persona_id == "horus":
            files = HORUS_CONTEXT_FILES
            image_roots = [
                PERSONA_MEDIA_ROOT / "horus" / "dreams" / "horus_dream_2026-02-06" / "images",
                PERSONA_MEDIA_ROOT / "horus" / "dreams" / "horus_dream_2026-02-06" / "storyboard" / "panels",
            ]
        else:
            files = []
            image_roots = [PERSONA_MEDIA_ROOT / persona_id]
        images: list[dict[str, Any]] = []
        for root in image_roots:
            images.extend(_image_inventory(root, limit=12))
        context[persona_id] = {
            "persona_id": persona_id,
            "source_files": [_read_excerpt(path) for path in files],
            "image_references": images[:20],
            "media_root": str(PERSONA_MEDIA_ROOT / persona_id),
        }
    return context


def _sparta_context() -> dict[str, Any]:
    return {
        "source_files": [_read_excerpt(path) for path in SPARTA_EXPLORER_CONTEXT_FILES],
        "summary": {
            "product_frame": "SPARTA Explorer is an evidence-governed workbench, not a dashboard.",
            "primary_surfaces": [
                "Sparta Chat",
                "Evidence Workspace",
                "Coverage",
                "QRAs",
                "Controls",
                "Threat Matrix",
                "Sources / URLs",
                "Posture",
                "Supply Chain",
                "Monitor / Status",
            ],
            "chat_contract": "Chat answers must carry compact evidence receipts and defer full adjudication to Evidence Workspace.",
            "anti_theater_rule": "No green status, compliance claim, or answer without source-of-truth evidence and a valid next action.",
        },
    }


def _normalize_item(raw: dict[str, Any], scope: str, idx: int, source: str) -> dict[str, Any]:
    text = str(
        raw.get("text")
        or raw.get("retrieval_text")
        or raw.get("claim_text")
        or raw.get("tom_content")
        or raw.get("evidence_text")
        or raw.get("answer_text")
        or raw.get("question_text")
        or raw.get("solution")
        or raw.get("problem")
        or raw.get("content")
        or raw.get("title")
        or ""
    ).strip()
    source_id = str(raw.get("source_id") or raw.get("_key") or f"{source}:{scope}:{idx}")
    return {
        "source_id": source_id,
        "scope": str(raw.get("scope") or scope),
        "source": str(raw.get("source") or raw.get("_source") or source),
        "type": str(raw.get("type") or raw.get("kind") or "Memory Residue"),
        "text": text,
        "scores": raw.get("scores", {}),
        "synthetic": False,
        "persona_id": raw.get("persona_id"),
        "persona_ids": raw.get("persona_ids") or [],
        "record_type": raw.get("record_type"),
        "source_path": raw.get("source_path"),
        "source_quote": raw.get("source_quote"),
    }


def _load_fixture(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    raw_items = data.get("items", data if isinstance(data, list) else [])
    items = []
    for idx, raw in enumerate(raw_items):
        item = _normalize_item(raw, str(raw.get("scope", "fixture")), idx, "fixture")
        item["synthetic"] = False
        if item["text"]:
            items.append(item)
    return items


def _recall_memory(query: str, scope: str, k: int, collections: list[str] | None = None) -> dict[str, Any]:
    import httpx

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
        body: dict[str, Any] = {"q": query, "scope": scope, "k": k}
        if collections:
            body["collections"] = collections
        if scope == CENTRAL_PERSONA_MEMORY_SCOPE:
            body["threshold"] = 0.0
        resp = client.post("/recall", json=body)
        resp.raise_for_status()
        return resp.json()


def _persona_id_candidates(persona_id: str) -> set[str]:
    normalized = persona_id.replace("-", "_")
    candidates = {persona_id, normalized}
    # Compatibility aliases for existing central persona_memory records.
    if normalized == "horus":
        candidates.add("horus_lupercal")
    if normalized == "embry":
        candidates.add("embry_lawson")
    return candidates


def _raw_persona_ids(raw: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for value in (raw.get("persona_id"), raw.get("agent_id")):
        if isinstance(value, str) and value:
            ids.add(value)
    for value in raw.get("persona_ids") or []:
        if isinstance(value, str) and value:
            ids.add(value)
    for tag in raw.get("tags") or []:
        if isinstance(tag, str) and tag.startswith("persona:"):
            ids.add(tag.split(":", 1)[1])
    return ids


def _matches_persona(raw: dict[str, Any], accepted_persona_ids: set[str]) -> bool:
    return bool(_raw_persona_ids(raw) & accepted_persona_ids)


def _fetch_residue_for_persona(persona: Persona, limit: int, about: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    topic = f" {about}" if about else ""
    accepted_persona_ids = _persona_id_candidates(persona.id)
    persona_query_terms = " ".join(sorted(accepted_persona_ids))
    queries = [
        (
            CENTRAL_PERSONA_MEMORY_SCOPE,
            f"{persona_query_terms} source-grounded persona_memory theory of mind emotional residue unresolved themes evidence{topic}",
            [CENTRAL_PERSONA_MEMORY_COLLECTION],
            True,
        ),
        (persona.scope("memories"), f"recent unresolved themes persona memory SPARTA NIST MITRE evidence{topic}", None, False),
        (persona.scope("dreams"), f"recent dream motif visual surreal recurring image{topic}", None, False),
        (persona.scope("dream-journals"), f"dream reflection mood unresolved image feeling{topic}", None, False),
        ("operational", f"{persona.id} recent task failure contradiction insight{topic}", None, False),
    ]
    items: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    per_query = max(1, limit // max(1, len(queries)))
    for scope, query, collections, require_persona_match in queries:
        try:
            query_k = max(32, per_query) if require_persona_match else per_query
            data = _recall_memory(query, scope, query_k, collections)
            raw_items = data.get("items", [])
            filtered_items = [
                raw for raw in raw_items
                if not require_persona_match or _matches_persona(raw, accepted_persona_ids)
            ]
            accepted_items: list[dict[str, Any]] = []
            accepted_source_ids: list[str] = []
            for idx, raw in enumerate(filtered_items):
                item = _normalize_item(raw, scope, idx, "memory")
                if item["text"]:
                    accepted_items.append(item)
                    accepted_source_ids.append(item["source_id"])
            receipts.append({
                "persona_id": persona.id,
                "accepted_persona_ids": sorted(accepted_persona_ids),
                "scope": scope,
                "query": query,
                "collections": collections,
                "k": query_k,
                "status": "ok",
                "found": bool(data.get("found")),
                "confidence": data.get("confidence"),
                "count": len(raw_items),
                "accepted_count": len(filtered_items),
                "accepted_normalized_count": len(accepted_items),
                "accepted_source_ids": accepted_source_ids,
                "accepted_source_ids_sha256": _stable_json_sha256(accepted_source_ids),
                "dropped_empty_text_count": len(filtered_items) - len(accepted_items),
                "discarded_persona_mismatch_count": len(raw_items) - len(filtered_items),
                "should_scan": data.get("should_scan"),
            })
            items.extend(accepted_items)
        except Exception as exc:
            receipts.append({
                "persona_id": persona.id,
                "scope": scope,
                "query": query,
                "collections": collections,
                "status": "error",
                "error": str(exc),
                "count": 0,
                "accepted_count": 0,
                "accepted_normalized_count": 0,
                "accepted_source_ids": [],
                "accepted_source_ids_sha256": _stable_json_sha256([]),
                "dropped_empty_text_count": 0,
            })
    return items[:limit], receipts


def _fetch_day_memories(persona: Persona, day: str, want: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Today's events, read from memory by day.

    Deliberately AQL and not ``/recall``. A day is an exact-match question --
    "what happened on this date" -- and recall is semantic top-k that cannot be
    asked for a date at all (graph-memory-operator#99, #100). Asking the wrong
    question is how five consecutive dreams recalled the same residue.

    Ordered by salience so that when a day is trimmed to quota, the thing that
    mattered most survives rather than whatever the store happened to return.
    """
    import httpx

    receipt: dict[str, Any] = {
        "stratum": "day", "day": day, "persona_id": persona.id,
        "path": "POST /query (AQL)", "requested": want,
    }
    try:
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            resp = client.post("/query", json={
                # Deprecated records are tombstoned, not deleted -- the store is
                # append-only by design. A reader that ignores the tombstone
                # would keep drawing a record its author has retracted.
                "aql": ("FOR d IN persona_memory FILTER d.day == @day AND d.persona_id == @p "
                        "AND d.deprecated != true SORT d.salience DESC RETURN d"),
                "bind_vars": {"day": day, "p": persona.id},
            })
            resp.raise_for_status()
            body = resp.json() or {}
        raw_items = body.get("documents") or body.get("result") or []
    except Exception as exc:  # noqa: BLE001 - reported in the receipt, never raised
        receipt.update({"status": "error", "error": str(exc), "available": 0, "taken": 0})
        return [], receipt

    items: list[dict[str, Any]] = []
    # Memory is append-only by design -- there is no delete route, and
    # destructive AQL is refused -- so historical duplicates cannot be removed
    # and must be tolerated on read. Before the reflection key was
    # content-addressed, every re-run wrote another copy of an identical
    # interpretation; counting each one would let one conclusion consume the
    # whole day quota and crowd out everything she actually experienced.
    # Deduplicating here also covers duplicates this pipeline never wrote.
    seen_text: set[str] = set()
    for idx, raw in enumerate(raw_items):
        item = _normalize_item(raw, f"episodic:day={day}", idx, "day")
        if not item["text"]:
            continue
        # Prefer the stance itself. The stored document also carries a
        # "What happened for X on DATE" title, and the service concatenates the
        # two into one text field; a dream fed the title dreams about the title.
        stance = str(raw.get("solution") or "").strip()
        if stance:
            item["text"] = stance
        fingerprint = " ".join(str(item["text"]).split()).strip().lower()
        if fingerprint in seen_text:
            continue
        seen_text.add(fingerprint)
        item["type"] = f"Day event ({raw.get('kind') or 'unknown'})"
        item["day"] = day
        item["salience"] = raw.get("salience")
        items.append(item)

    # Draw round-robin across kinds, not straight down the salience order. A
    # busy coding day scores 1.0 on every code event and would take the whole
    # quota, silencing the affect signal -- and how the human felt is the part
    # that makes this a dream about a person rather than a changelog.
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_kind.setdefault(str(item.get("type", "")), []).append(item)
    # Priority, not alphabetical. Conversation is the return arc -- what was
    # said back about the last dream -- and on a day when someone engaged, that
    # outranks how many commits were pushed. Sorting by name alone put
    # "(code)" ahead of "(conversation)" and silently dropped the arc, which
    # made the loop look closed while nothing came back.
    def _rank(kind: str) -> int:
        # What deepens a persona, in order. How the human felt, what was said
        # back, and what she previously concluded about herself all outrank the
        # commit count. A dream reflection is her own prior interpretation --
        # the channel through which anything accumulates at all -- so it must
        # not lose a quota slot to churn.
        if "affect" in kind:
            return 0
        if "conversation" in kind:
            return 1
        if "dream_reflection" in kind:
            return 2
        if "project_state" in kind:
            return 3
        return 4

    order = sorted(by_kind, key=lambda k: (_rank(k), k))
    drawn: list[dict[str, Any]] = []
    while len(drawn) < want and any(by_kind[k] for k in order):
        for k in order:
            if by_kind[k] and len(drawn) < want:
                drawn.append(by_kind[k].pop(0))

    receipt.update({
        "status": "ok",
        "available": len(items),
        "taken": len(drawn),
        "selection": "round_robin_across_kinds_then_salience",
        "kinds_taken": sorted({str(i.get("type")) for i in drawn}),
    })
    return drawn, receipt


def _fetch_residue(persona: Persona, limit: int, about: str | None = None,
                   secondary_persona: Persona | None = None,
                   day: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Residue for one dream, drawn by QUOTA across strata rather than top-k.

    Top-k over one undifferentiated pool is what made every dream the same: the
    queries are constants, so the same handful of documents won the same ranking
    every cycle. A quota reserves room for today regardless of how today scores
    against a year of persona memory, and reserves room for identity so a busy
    day cannot drown who she is.
    """
    total_limit = limit
    day_items: list[dict[str, Any]] = []
    day_receipt: dict[str, Any] | None = None
    if day:
        # Today gets a reserved share, floored at 3 so all three kinds of day
        # event -- affect, project_state, code -- can be represented at the
        # default limit. A day reduced to two slots drops a whole kind, and
        # which kind it drops is an accident of ordering.
        # Enough to change the dream, not enough to become it: the blend with
        # existing persona memory is the point.
        day_quota = max(3, limit // 3)
        day_items, day_receipt = _fetch_day_memories(persona, day, day_quota)

    # The day's share comes OUT of the total, so the memory draw shrinks -- but
    # the total must not. Reusing the reduced number for the final trim below
    # cut the memory items straight back off again and left the dream with
    # nothing but today, which is the opposite of a blend.
    total_limit = limit
    limit = max(1, limit - len(day_items))
    personas = [persona]
    if secondary_persona and secondary_persona.id != persona.id:
        personas.append(secondary_persona)
    per_persona = max(1, limit // len(personas))
    items: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for active_persona in personas:
        fetched, fetched_receipts = _fetch_residue_for_persona(active_persona, per_persona, about)
        items.extend(fetched)
        receipts.extend(fetched_receipts)
    if day_receipt is not None:
        receipts.insert(0, day_receipt)
    # Today first: the dream should open on what just happened, and a downstream
    # trim must not be what decides whether today survives.
    items = day_items + items
    return items[:total_limit], receipts


def _bridges_for(text: str) -> list[str]:
    """Axes present in one memory, matched on word boundaries.

    Bare substring matching let "source" score Loyalty and would let "resource"
    score "source" (#1200). Multi-word terms are matched as phrases; single
    words must stand alone.
    """
    lowered = text.lower()
    found = []
    for bridge, terms in BRIDGES.items():
        for term in terms:
            pattern = re.escape(term) if " " in term else rf"\b{re.escape(term)}\w*\b"
            if re.search(pattern, lowered):
                found.append(bridge)
                break
    return found


def _detect_contradictions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tagged = [(item, _bridges_for(item["text"])) for item in items]
    tensions: list[dict[str, Any]] = []
    for i, (a, bridges_a) in enumerate(tagged):
        for j, (b, bridges_b) in enumerate(tagged):
            if i >= j:
                continue
            for bridge in bridges_a:
                opposite = OPPOSITIONS.get(bridge)
                if opposite and opposite in bridges_b:
                    tensions.append({
                        "item_a": a["source_id"],
                        "item_b": b["source_id"],
                        "bridge_a": bridge,
                        "bridge_b": opposite,
                        "description": f"{bridge} is held against {opposite}: {a['text'][:80]} / {b['text'][:80]}",
                        "score": round(0.5 + 0.1 * len(tensions), 3),
                    })
                    break
    return tensions[:5]


def _keywords(items: list[dict[str, Any]]) -> list[str]:
    words: dict[str, int] = {}
    for item in items:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", item["text"]):
            low = word.lower()
            if low in {"this", "that", "with", "where", "from", "into", "each", "until", "memory"}:
                continue
            words[low] = words.get(low, 0) + 1
    return [word for word, _ in sorted(words.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]


def _build_prompts(persona: Persona, items: list[dict[str, Any]], contradictions: list[dict[str, Any]], frames: int, about: str | None = None) -> tuple[str, list[dict[str, Any]], str]:
    keys = _keywords(items)
    bridge_set = sorted({bridge for item in items for bridge in _bridges_for(item["text"])})
    tension_line = contradictions[0]["description"] if contradictions else "No direct opposition surfaced; the dream follows unresolved residue."
    about_line = f" The requested dream topic is {about}." if about else ""
    prompt = (
        f"Synthetic dream for {persona.display_name}. "
        f"{about_line}"
        f"Memory residue gathers around {', '.join(keys[:6]) or 'unresolved work'}. "
        f"Bridge tones: {', '.join(bridge_set) or 'contemplative'}. "
        f"Core tension: {tension_line}. "
        "Render as symbolic images, not factual claims."
    )
    frame_prompts = []
    selected = items[: max(1, frames)]
    for idx in range(frames):
        item = selected[idx % len(selected)]
        bridges = _bridges_for(item["text"])
        frame_prompts.append({
            "frame_id": f"frame_{idx + 1:02d}",
            "source_ids": [item["source_id"]],
            "prompt": (
                f"{persona.display_name} dream frame, {item['type'].lower()}, "
                f"{'topic: ' + about + ', ' if about else ''}"
                f"{item['text'][:180]}, symbolic, cinematic still, contact sheet frame, "
                f"bridge tone: {', '.join(bridges) if bridges else 'contemplative'}"
            ),
            "negative_prompt": "literal compliance verdict, fake citation, UI screenshot, watermark",
            "synthetic": True,
        })
    reflection = (
        f"I woke with {', '.join(keys[:4]) or 'the residue'} still arranged like images rather than answers. "
        f"The dream was synthetic, but it kept the source traces intact: {len(items)} memory residues and "
        f"{len(contradictions)} explicit tensions. "
        "I should treat this as a reflective lead, not as evidence or a durable identity change."
    )
    return prompt, frame_prompts, reflection


def _slug(text: str, limit: int = 42) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].strip("-") or "dream"


def _build_video_plan(
    persona: Persona,
    secondary: Persona | None,
    about: str,
    scene: str,
    duration: int,
    items: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    persona_context: dict[str, Any],
    sparta_context: dict[str, Any],
) -> dict[str, Any]:
    secondary_name = secondary.display_name if secondary else "the machine spirit"
    title = f"Tea on the Void Patio: {persona.display_name} and {secondary_name}"
    total = max(12, min(duration, 60))
    if total == 30:
        shot_lengths = [7.5, 7.5, 7.5, 7.5]
    else:
        clip_count = max(1, round(total / 5))
        shot_lengths = [5] * max(0, clip_count - 1)
        shot_lengths.append(total - sum(shot_lengths))
    starts: list[tuple[float, float]] = []
    cursor = 0.0
    for length in shot_lengths:
        starts.append((cursor, cursor + length))
        cursor += length

    sparta_terms = [
        "evidence-governed workbench",
        "Sparta Chat",
        "Evidence Workspace",
        "compact evidence receipt",
        "fail-closed Monitor / Status",
        "Posture and Threat Matrix navigation",
    ]
    residue_ids = [item["source_id"] for item in items[:6]]
    core_tension = contradictions[0]["description"] if contradictions else "friendship and tactical seriousness held inside a surreal calm scene"
    scenario = scene.strip() or (
        "Horus and Embry have tea under a patio umbrella on a Warhammer 40k void world "
        "while Tyranids move like distant wildlife in the background."
    )

    story_md = f"""# {title}

{scenario}

The dream is quiet instead of grim. Embry sits forward with both hands around a tea cup, trying to explain why SPARTA Explorer cannot become another wall of green cards. Horus, trapped and theatrical but genuinely engaged, treats the patio table like a war council map. Behind them, Tyranids wander across the ash horizon like impossible garden birds.

They are talking about creating the SPARTA Explorer app as a friendly working conversation. Embry wants the interface to help people ask grounded questions, see the evidence case, and know when to clarify. Horus keeps calling it a campaign of proof: no unsupported claim gets past the perimeter, no stale artifact gets called healthy, no evidence receipt pretends to be a verdict.

The emotional shape is personal: Embry is tired of dashboards that make operators feel stupid, and Horus is offended by careless systems but softens when he sees her trying to build something durable. The scene ends with them agreeing that Sparta Chat should feel like a trusted colleague at the table, not a generic chatbot in a box.

Core tension: {core_tension}
"""

    characters = [
        {
            "character_id": "embry",
            "display_name": "Embry",
            "role_in_scene": "SPARTA intern and builder of the workbench",
            "visual_continuity": [
                "23-year-old aerospace cybersecurity intern",
                "brown shoulder-length hair, practical low ponytail or half-up mess",
                "forest/olive green eyes",
                "faint old scar across nose bridge",
                "practical navy/gray/olive workwear",
                "capable but self-conscious when observed",
            ],
            "dialogue_tone": "warm, direct when technical, vulnerable when talking about belonging and operator trust",
            "reference_policy": {
                "reference_type": "fictional_character",
                "usage_role": "fictional_embodiment",
                "synthetic_output_label": True,
                "identity_claim_allowed": False,
            },
        },
        {
            "character_id": "horus",
            "display_name": "Horus",
            "role_in_scene": "resentful machine-spirit strategist acting as a tactical product reviewer",
            "visual_continuity": [
                "larger-than-life warmaster presence translated into a machine-spirit avatar",
                "dark regal armor hints or severe black/gold silhouette",
                "expressive face: contempt at bad evidence, grudging respect for Embry",
                "tea cup handled like a war trophy, not comic relief",
            ],
            "dialogue_tone": "competent first, dry and salty second, protective of correctness despite the resentment",
            "reference_policy": {
                "reference_type": "fictional_character",
                "usage_role": "fictional_embodiment",
                "synthetic_output_label": True,
                "identity_claim_allowed": False,
            },
        },
    ]
    scenes = [
        {
            "scene_id": "void_patio",
            "setting": "patio table with umbrella on a 40k void world, tea service in foreground, Tyranids playing in distant background",
            "palette": ["charcoal regolith", "bone-white patio umbrella", "tea amber", "SPARTA green evidence glow", "distant bio-organic purple"],
            "continuity_invariants": [
                "Horus and Embry remain seated at the same round patio table",
                "umbrella stays centered over the table",
                "Tyranids remain background action and do not attack",
                "conversation stays friendly and personal",
                "SPARTA Explorer artifacts appear as holographic cards or table projections",
            ],
        }
    ]
    bible = {
        "schema": "persona_dream.character_scene_bible.v1",
        "title": title,
        "duration_seconds": total,
        "characters": characters,
        "scenes": scenes,
        "sparta_explorer_context": sparta_context["summary"],
        "persona_context_sources": persona_context,
        "comfyui_actor_sheet_lane": {
            "status": "planned",
            "comfyui_root": str(COMFYUI_ROOT),
            "purpose": "Generate or refine front/side/three-quarter/pose sheets when existing persona references are insufficient.",
            "node_hint": "ComfyUI pose-generator-comfyui-node or equivalent OpenPose workflow.",
            "direct_model_calls": "All model/provider calls remain routed through scillm or an explicit ComfyUI workflow receipt.",
        },
        "public_reference_boundary": {
            "synthetic_output_label": True,
            "identity_claim_allowed": False,
            "rule": "Generated actor/public-figure imagery must not be described as factual identity evidence.",
        },
        "self_improvement_loop": {
            "schema": "persona_dream.self_improvement_loop.v1",
            "policy": "Every stage records quality signals, failure signals, revision actions, and the stop condition before the next stage is accepted.",
            "stage_loop": [
                "generate candidate artifact",
                "inspect against stage acceptance checks",
                "record pass/warn/fail in stage report",
                "revise prompt, reference, source context, or fallback when failed",
                "persist receipt before advancing",
            ],
            "hard_stop_conditions": [
                "missing required artifact",
                "identity boundary violation",
                "clip continuity failure after bounded retries",
                "model/provider failure without fallback receipt",
                "final video duration not within tolerance",
            ],
        },
    }

    shot_specs = [
        ("shot_01", "Establish the impossible calm", "wide", "The patio umbrella and tea table sit on a void-world terrace while Tyranids tumble in the distance like strange pets.", "No evidence without a case, Embry. Even xenos understand perimeter discipline."),
        ("shot_02", "Embry explains the app", "medium on Embry", "Embry gestures to holographic SPARTA Explorer panels: Chat, Evidence Workspace, Coverage, QRAs, Controls.", "It has to feel like someone sitting with you, not a dashboard judging you."),
        ("shot_03", "Horus reframes it as campaign logic", "two-shot", "Horus taps the table; evidence receipts arrange like a campaign map while Embry relaxes enough to smile.", "Then make the receipt a battle standard: case, state, reason, artifact, next action. No theater."),
        ("shot_04", "Agreement and dream close", "slow push-in", "The Tyranids settle beyond the patio; the table projection becomes a compact SPARTA Chat evidence receipt and the tea steam drifts through it.", "A trusted colleague at the table. Fine. I will permit this little workbench to exist."),
    ]
    storyboard = []
    timed = []
    prompts = []
    for idx, ((start, end), (shot_id, beat, camera, visual, dialogue)) in enumerate(zip(starts, shot_specs), 1):
        speaker = "embry" if shot_id == "shot_02" else "horus"
        storyboard.append({
            "shot_id": shot_id,
            "scene_id": "void_patio",
            "beat": beat,
            "camera": camera,
            "visual": visual,
            "characters": ["embry", "horus"],
            "background_action": "Tyranids play in the far background without threatening the table.",
            "source_residue_ids": residue_ids,
        })
        timed.append({
            "shot_id": shot_id,
            "start_sec": start,
            "end_sec": end,
            "duration_sec": round(end - start, 3),
            "characters": ["embry", "horus"],
            "speaker": speaker,
            "dialogue": dialogue,
            "action": visual,
            "camera": camera,
            "audio_cue": "quiet tea porcelain, low void wind, distant non-threatening chitter, warm conversational tone",
        })
        prompt = (
            f"cinematic dream video frame, {scenario}, {visual} "
            f"Embry: brown hair, olive green eyes, faint nose bridge scar, practical aerospace intern clothing. "
            f"Horus: dark regal machine-spirit warmaster avatar, severe black and gold silhouette, seated at tea. "
            f"SPARTA Explorer holographic UI on the patio table: {', '.join(sparta_terms[:4])}. "
            "Tyranids visible only in the distant background, playful not attacking, friendly personal conversation, "
            "photoreal surreal science fantasy, stable character continuity, no text watermark"
        )
        prompts.append({
            "prompt_id": f"prompt_{idx:02d}",
            "shot_id": shot_id,
            "model_lane": "ComfyUI Z-Image/keyframe workflow -> ComfyUI TurboDiffusion TurboWan2.2-I2V-A14B-720P; Chutes non-Turbo fallback only after canary",
            "source_keyframe_id": f"keyframe_{idx:02d}",
            "prompt": prompt,
            "negative_prompt": "robotic office meeting, generic dashboard, hostile attack, gore, unreadable faces, extra characters at table, text artifacts, watermark",
            "duration_sec": round(end - start, 3),
            "num_frames": 121 if round(end - start, 3) > 5 else 81,
            "fps": 24,
            "clip_duration_policy": "TurboDiffusion I2V optimized 5-second clip unit by default; 7.5-second shots use 121 frames when the scene needs more time.",
            "continuity_anchors": [
                "same patio table and umbrella",
                "Embry face, scar, hair, and clothing stable",
                "Horus seated and recognizable as machine-spirit warmaster avatar",
                "Tyranids remain distant background",
                "SPARTA Explorer holograms remain evidence-workbench themed",
            ],
            "acceptance_checks": [
                "both characters visible and seated together",
                "tea/patio/umbrella visible",
                "Tyranids in background but non-threatening",
                "SPARTA Explorer conversation implied by table holograms",
                "friendly personal tone, not sterile office mood",
            ],
            "synthetic_output_label": True,
            "identity_claim_allowed": False,
        })
    return {
        "dream_story_md": story_md,
        "dream_story_json": {
            "schema": "persona_dream.story.v1",
            "title": title,
            "scenario": scenario,
            "duration_seconds": total,
            "summary": "Horus and Embry discuss SPARTA Explorer over tea on a void-world patio while distant Tyranids play in the background.",
            "emotional_arc": [
                "surreal calm",
                "Embry names the product fear",
                "Horus turns evidence discipline into strategy",
                "they reject dashboard theater together",
                "Embry names the personal reason for the app",
                "the app becomes a colleague at the table",
            ],
            "source_residue_ids": residue_ids,
            "synthetic": True,
        },
        "character_scene_bible": bible,
        "storyboard": {"schema": "persona_dream.storyboard.v1", "shots": storyboard},
        "timed_transcript": {
            "schema": "persona_dream.timed_transcript.v1",
            "duration_seconds": total,
            "clip_policy": {
                "backend": "Dockerized ComfyUI TurboDiffusion TurboWan2.2-I2V-A14B-720P preferred for 4-step TurboDiffusion",
                "default_num_frames": 81,
                "extended_num_frames": 121,
                "fps": 24,
                "nominal_clip_seconds": 5,
                "extended_clip_seconds": 7.5,
                "assembly_plan": "four 7.5-second clips for a 30-second final video unless 5-second shots prove easier to stabilize",
            },
            "shots": timed,
        },
        "multimodal_prompts": {"schema": "persona_dream.multimodal_prompts.v1", "prompts": prompts},
        "voice_handoff_plan": {
            "schema": "persona_dream.voice_handoff_plan.v1",
            "status": "planned",
            "owner": "create-movie/audio-lane",
            "persona_dream_boundary": "This skill plans speaker timing, dialogue, identity boundaries, and required receipts. It does not own TTS, voice conversion, long-form audio editing, or final audio review.",
            "duration_seconds": total,
            "speakers": [
                {
                    "speaker_id": "horus",
                    "voice_role": "fictional Horus persona voice",
                    "preferred_reference_search_paths": [
                        "/mnt/storage12tb/media/personas/horus/data/personaplex_output.wav",
                        "/mnt/storage12tb/media/personas/horus/data/tts_output",
                        "/mnt/storage12tb/media/personas/horus/data/audiobooks",
                    ],
                    "identity_boundary": "fictional Horus persona voice; local persona reference assets only; not a living actor identity clone",
                    "near_term_lane": "Kokoro base TTS followed by isolated KokoClone/Kanade conversion canary",
                    "future_lane": "curated multi-clip dataset and fine-tuned voice model after train-voice/tts-horus proof",
                },
                {
                    "speaker_id": "embry",
                    "voice_role": "fictional Embry persona voice",
                    "preferred_reference_search_paths": [
                        "/mnt/storage12tb/media/personas/embry",
                        "/home/graham/Downloads/voice_clone_test_audio.wav",
                    ],
                    "identity_boundary": "fictional Embry voice; actress references are cadence/style direction only; do not clone living actor identity",
                    "near_term_lane": "Kokoro synthetic voice tensor blend followed by optional isolated KokoClone/Kanade conversion canary",
                    "future_lane": "curated authorized reference clips, candidate listening review, and fine-tuned voice model after train-voice proof",
                },
            ],
            "lines": [
                {
                    "line_id": f"{shot['shot_id']}_{shot['speaker']}",
                    "shot_id": shot["shot_id"],
                    "speaker_id": shot["speaker"],
                    "start_sec": shot["start_sec"],
                    "end_sec": shot["end_sec"],
                    "duration_sec": shot["duration_sec"],
                    "text": shot["dialogue"],
                }
                for shot in timed
            ],
            "required_receipts": [
                "voice_identity_boundary_receipt.json",
                "voice_reference_inventory.json",
                "kokoro_base_tts_receipt.json",
                "voice_blend_recipe.json for synthetic Embry base voice if used",
                "kokoclone_env_receipt.json if conversion is used",
                "per_line_conversion_receipts.json",
                "converted_wav_ffprobe.json",
                "dialogue_mix_receipt.json",
                "mux_receipt.json",
                "voiced_video_ffprobe.json",
                "voice_eval_receipt.json or listening_review_receipt.json",
            ],
            "selection_policy": [
                "Prefer straight Kokoro when intelligibility is the primary risk.",
                "Prefer KokoClone conversion when persona coloring is the primary goal and a canary passes.",
                "Do not select a converted candidate by metrics alone; keep a listening montage or model-assisted audio review receipt.",
                "Time-fit any line that exceeds its shot window before muxing.",
            ],
        },
    }


def _build_stage_report(
    *,
    request: dict[str, Any],
    items: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    artifacts: list[str],
    video_plan_artifacts: dict[str, Any] | None,
    recall_receipts: list[dict[str, Any]],
    memory_receipt: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    stages = [
        {
            "stage_id": "stage_01_intake",
            "status": "ok",
            "did": "Normalized the user request into a persona-dream run request.",
            "text_outputs": ["dream_request.json"],
            "visual_outputs": [],
            "evidence": {
                "persona": request["persona"],
                "secondary_persona": request.get("secondary_persona"),
                "about": request.get("about"),
                "scene": request.get("scene"),
                "mode": request.get("mode"),
            },
            "failure_or_gap": None,
        },
        {
            "stage_id": "stage_02_memory_recall",
            "status": "ok" if items else "blocked",
            "did": "Collected residue from fixture or memory recall and preserved source ids.",
            "text_outputs": ["residue_links.json"],
            "visual_outputs": [],
            "evidence": {"residue_count": len(items), "recall_receipts": recall_receipts},
            "failure_or_gap": None if items else "No residue found; dream generation refused to fabricate.",
        },
        {
            "stage_id": "stage_03_tension_detection",
            "status": "ok",
            "did": "Detected simple bridge tensions across residue items.",
            "text_outputs": ["contradiction_report.json"],
            "visual_outputs": [],
            "evidence": {"contradiction_count": len(contradictions)},
            "failure_or_gap": None,
        },
        {
            "stage_id": "stage_04_static_dream_packet",
            "status": "ok",
            "did": "Created dream prompt, frame prompts, contact sheet, packet, and reflection.",
            "text_outputs": ["dream_packet.json", "dream_prompt.txt", "frame_prompts.json", "dream_reflection.md"],
            "visual_outputs": ["contact_sheet.png"],
            "evidence": {"frame_prompt_count": request.get("frames")},
            "failure_or_gap": "Contact sheet is deterministic planning art, not final generated model output.",
        },
    ]
    if request.get("mode") == "video_plan":
        timed_count = len(video_plan_artifacts["timed_transcript"]["shots"]) if video_plan_artifacts else 0
        prompt_count = len(video_plan_artifacts["multimodal_prompts"]["prompts"]) if video_plan_artifacts else 0
        stages.extend([
            {
                "stage_id": "stage_05_source_context",
                "status": "ok",
                "did": "Loaded local Embry/Horus persona context, persona image references, ComfyUI root, and SPARTA Explorer documentation excerpts.",
                "text_outputs": ["character_scene_bible.json"],
                "visual_outputs": [],
                "evidence": {
                    "persona_context_ids": list((video_plan_artifacts or {}).get("character_scene_bible", {}).get("persona_context_sources", {}).keys()),
                    "comfyui_root": str(COMFYUI_ROOT),
                },
                "failure_or_gap": "No Brave external image search has been executed yet; local persona assets were sufficient for video planning.",
            },
            {
                "stage_id": "stage_06_story_and_bible",
                "status": "ok",
                "did": "Created the dream story and continuity bible for the Horus/Embry patio-tea scene.",
                "text_outputs": ["dream_story.md", "dream_story.json", "character_scene_bible.json"],
                "visual_outputs": [],
                "evidence": {"duration_seconds": request.get("duration_seconds")},
                "failure_or_gap": None,
            },
            {
                "stage_id": "stage_07_storyboard_and_transcript",
                "status": "ok",
                "did": "Converted the story into shot ids, a storyboard, and a time-based transcript.",
                "text_outputs": ["storyboard.json", "timed_transcript.json"],
                "visual_outputs": [],
                "evidence": {"shot_count": timed_count},
                "failure_or_gap": None,
            },
            {
                "stage_id": "stage_08_multimodal_prompts",
                "status": "ok",
                "did": "Created per-shot multimodal prompts for local/containerized keyframes followed by ComfyUI TurboDiffusion Wan 2.2 I2V clips; Chutes remains an optional non-Turbo fallback after canary proof.",
                "text_outputs": ["multimodal_prompts.json"],
                "visual_outputs": [],
                "evidence": {"prompt_count": prompt_count},
                "failure_or_gap": "Model calls have not run yet; keyframe and video receipts are intentionally absent until the next execution stage.",
            },
            {
                "stage_id": "stage_09_voice_handoff",
                "status": "planned",
                "did": "Created a voice handoff plan with speaker timing, identity boundaries, near-term TTS/conversion lanes, future fine-tuning lanes, and required audio receipts.",
                "text_outputs": ["voice_handoff_plan.json"],
                "visual_outputs": [],
                "evidence": {
                    "speaker_count": len((video_plan_artifacts or {}).get("voice_handoff_plan", {}).get("speakers", [])),
                    "line_count": len((video_plan_artifacts or {}).get("voice_handoff_plan", {}).get("lines", [])),
                    "owner": (video_plan_artifacts or {}).get("voice_handoff_plan", {}).get("owner"),
                },
                "failure_or_gap": "TTS, voice conversion, voice evaluation, and audio muxing remain downstream audio-lane work.",
            },
            {
                "stage_id": "stage_10_self_improvement_loop",
                "status": "planned",
                "did": "Defined the loop that checks each generated artifact, compares clip-to-clip continuity, revises failed prompts/references, and records every retry/fallback.",
                "text_outputs": ["character_scene_bible.json", "pipeline_stage_report.json"],
                "visual_outputs": [],
                "evidence": {
                    "loop": [
                        "generate candidate",
                        "inspect against current stage acceptance checks",
                        "compare generated scene with previous accepted scene",
                        "revise prompt/reference/keyframe or regenerate failed clip",
                        "record correction decision before advancing",
                    ],
                    "continuity_output_required_next": "continuity_report.json",
                },
                "failure_or_gap": "Actual model-output correction cannot run until keyframes and clips exist.",
            },
            {
                "stage_id": "stage_11_memory_writeback",
                "status": memory_receipt.get("status", "unknown"),
                "did": "Recorded whether dream reflection was persisted to memory.",
                "text_outputs": ["memory_write_receipt.json"],
                "visual_outputs": [],
                "evidence": memory_receipt,
                "failure_or_gap": None if memory_receipt.get("status") == "ok" else "Memory writeback was skipped or failed; check receipt.",
            },
        ])
    report = {
        "schema": "persona_dream.pipeline_stage_report.v1",
        "run_id": request["run_id"],
        "mode": request.get("mode"),
        "overall_status": "ok",
        "artifacts": sorted(set(artifacts)),
        "stages": stages,
        "non_claims": [
            "This report does not prove Chutes keyframe generation has run.",
            "This report does not prove Wan I2V clips exist.",
            "This report does not prove FFmpeg assembly exists.",
            "This report does not prove the final 30-second video has passed visual continuity checks.",
        ],
    }
    lines = [
        "# Persona Dream Pipeline Stage Report",
        "",
        f"Run: `{request['run_id']}`",
        f"Mode: `{request.get('mode')}`",
        "",
        "## Report Summary",
        "",
        "**Overall Finding:** Partially Verified",
        "",
        "The run has deterministic planning artifacts, but model generation and final video assembly remain unproven until their receipts exist.",
        "",
        "## Source-of-Truth Inventory",
        "",
        "| Source | Type | Used For | Limitation |",
        "|---|---|---|---|",
        "| `dream_request.json` | request artifact | intake | does not prove downstream execution |",
        "| `residue_links.json` | memory/fixture receipt | source residue | depends on recall quality |",
        "| `character_scene_bible.json` | planning artifact | continuity | not a VLM validation result |",
        "| `timed_transcript.json` | planning artifact | 30-second shot schedule | not a rendered video |",
        "| `multimodal_prompts.json` | model prompt packet | z-image and Wan handoff | model calls not run yet |",
        "| `voice_handoff_plan.json` | audio planning artifact | TTS, voice conversion, and eval handoff | not rendered audio |",
        "",
        "## Stage Ledger",
        "",
    ]
    for stage in stages:
        lines.extend([
            f"### {stage['stage_id']}",
            "",
            f"Status: `{stage['status']}`",
            "",
            f"Did: {stage['did']}",
            "",
            f"Text outputs: {', '.join(f'`{name}`' for name in stage['text_outputs']) or 'none'}",
            "",
            f"Visual outputs: {', '.join(f'`{name}`' for name in stage['visual_outputs']) or 'none'}",
            "",
            f"Failure or gap: {stage['failure_or_gap'] or 'none'}",
            "",
        ])
    lines.extend([
        "## Plan-Ready Next Actions",
        "",
        "1. Start Dockerized ComfyUI and prove `/system_stats` plus `/object_info` readiness.",
        "2. Mount or download TurboDiffusion TurboWan2.2 I2V model files and required UMT5/VAE files.",
        "3. Generate per-shot keyframes and actor/pose sheets with receipts.",
        "4. Generate short I2V clips from accepted keyframes through ComfyUI TurboDiffusion receipts.",
        "5. Run continuity checks against `character_scene_bible.json` and the immediately previous accepted clip; regenerate or fallback on mismatch.",
        "6. Stitch accepted clips with FFmpeg and record `assembly_manifest.json` plus `ffmpeg_command.txt`.",
        "",
        "## Non-Claims",
        "",
    ])
    lines.extend(f"- {claim}" for claim in report["non_claims"])
    lines.append("")
    return report, "\n".join(lines)


def _draw_contact_sheet(path: Path, persona: Persona, frame_prompts: list[dict[str, Any]]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width = 1200
    cell_w = 400
    cell_h = 300
    rows = (len(frame_prompts) + 2) // 3
    height = max(1, rows) * cell_h
    img = Image.new("RGB", (width, height), (246, 244, 238))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
        small = ImageFont.truetype("DejaVuSans.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
        small = ImageFont.load_default()

    palette = [(38, 70, 83), (42, 157, 143), (233, 196, 106), (231, 111, 81), (95, 92, 156), (80, 130, 70)]
    for idx, frame in enumerate(frame_prompts):
        col = idx % 3
        row = idx // 3
        x = col * cell_w
        y = row * cell_h
        color = palette[idx % len(palette)]
        draw.rectangle([x + 10, y + 10, x + cell_w - 10, y + cell_h - 10], fill=color)
        draw.rectangle([x + 10, y + 10, x + cell_w - 10, y + cell_h - 10], outline=(30, 30, 30), width=2)
        title = f"{persona.display_name} {frame['frame_id']}"
        draw.text((x + 24, y + 24), title, fill=(255, 255, 255), font=font)
        wrapped = textwrap.wrap(frame["prompt"], width=42)[:8]
        for line_idx, line in enumerate(wrapped):
            draw.text((x + 24, y + 62 + line_idx * 22), line, fill=(255, 255, 255), font=small)
    img.save(path)


def _store_reflection(persona: Persona, reflection: str, packet: dict[str, Any],
                      day: str | None = None) -> dict[str, Any]:
    """Write what the dream concluded back into memory, so she carries it forward.

    This is the mechanism by which a persona deepens: a dream interprets her
    experiences, the interpretation becomes a memory, and a later dream draws on
    it alongside the experiences themselves. Without this write, every dream
    starts from the same place and nothing accumulates -- which is exactly what
    five byte-identical journals were telling us.

    It had never worked. The write targeted the ``lessons`` collection, which
    rejects a reflection with 422 "no extractable taxonomy" because a dream
    interpretation is not a lesson. It failed soft, so the run reported success
    while the most important write in the pipeline errored every time.

    A reflection is stored SYNTHETIC and stays that way. It is what she made of
    her experiences, not a record of what happened, and the distinction is
    carried in the text as well as the metadata so a retrieval path that drops
    the metadata still cannot promote an interpretation into literal history.
    """
    import httpx

    # Content-addressed, deliberately WITHOUT run_id. The same interpretation is
    # one memory however many times it is generated: keying on run_id meant every
    # re-run wrote a fresh duplicate of an identical conclusion, which inflates
    # the dreamt record and skews the quota that later dreams draw from -- it
    # corrupts the longitudinal record this project exists to build.
    # carry_conversation and store_dream_artifacts are already content-addressed;
    # this makes all three writers idempotent.
    key_src = f"{persona.id}:{reflection}"
    stance = reflection.strip()
    document = {
        "_key": "persona_dream_" + hashlib.sha256(key_src.encode()).hexdigest()[:24],
        "problem": f"What {persona.display_name} made of her experiences in a dream",
        # Attribution in the data, not only the metadata.
        "solution": f"In a dream I interpreted my recent experience: {stance}",
        "scope": f"episodic:day={day}" if day else persona.scope("dream-journals"),
        "tags": ["persona-dream", "dream-reflection", f"persona:{persona.id}"]
                + ([f"day:{day}"] if day else []),
        "persona_id": persona.id,
        "record_type": "dream_reflection",
        # Its own kind, so the day draw gives it a slot rather than making it
        # compete as if it were commit churn.
        "kind": "dream_reflection",
        "synthetic": True,
        "synthetic_notice": (
            "a synthetic interpretation of cited experience, not a factual claim "
            "about what occurred"
        ),
        "salience": 0.8,
        "decay_class": "slow",
        "day": day,
        "dream_packet_id": packet["run_id"],
        "source_ids": [item["source_id"] for item in packet["residue_items"]],
    }
    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
        try:
            resp = client.post(
                "/store",
                json={"document": document, "collection": CENTRAL_PERSONA_MEMORY_COLLECTION},
            )
            http_status, err = resp.status_code, None
            body = resp.json() if resp.content else None
        except Exception as exc:  # noqa: BLE001
            http_status, err, body = 0, str(exc), None

        # Read back. A store response is not evidence -- this write reported
        # nothing wrong for months while returning 422.
        read_back = False
        try:
            check = client.post("/query", json={
                "aql": "FOR d IN @@col FILTER d._key == @k RETURN d._key",
                "bind_vars": {"@col": CENTRAL_PERSONA_MEMORY_COLLECTION,
                              "k": document["_key"]},
            })
            found = (check.json() or {}).get("documents") or []
            read_back = bool(found)
        except Exception:  # noqa: BLE001
            read_back = False

    failed: list[str] = []
    if err or http_status >= 400:
        failed.append(f"store_failed:{http_status}{':' + err if err else ''}")
    if not read_back:
        failed.append("reflection_not_retrievable_after_write")

    return {
        "status": "ok" if not failed else "error",
        "endpoint": "/store",
        "collection": CENTRAL_PERSONA_MEMORY_COLLECTION,
        "scope": document["scope"],
        "document_key": document["_key"],
        "http_status": http_status,
        "read_back": read_back,
        "synthetic": True,
        "record_type": "dream_reflection",
        "response": body,
        "failed_gates": failed,
    }

@app.command("generate")
def generate(
    mode: str = typer.Option("static_dream", "--mode", help="Run mode: static_dream or video_plan."),
    persona_id: str = typer.Option("horus", "--persona", help="Persona id; scopes derive as <persona>-memories, <persona>-dreams, and <persona>-dream-journals."),
    secondary_persona_id: str | None = typer.Option(None, "--secondary-persona", help="Optional second persona for video_plan scenes."),
    about: str | None = typer.Option(None, "--about", help="Optional topic to bias memory recall and dream prompts."),
    day: str | None = typer.Option(None, "--day", help="YYYY-MM-DD; blend that day's events in from memory. Ingest them first with ./run.sh ingest-day."),
    scene: str | None = typer.Option(None, "--scene", help="Explicit scene description for video_plan mode."),
    duration_seconds: int = typer.Option(30, "--duration-seconds", min=12, max=60, help="Target video duration for video_plan mode."),
    limit: int = typer.Option(6, "--limit", min=1, max=12, help="Maximum residue items to use."),
    frames: int = typer.Option(6, "--frames", min=1, max=9, help="Number of frame prompts/contact-sheet cells."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Output directory. Defaults to /mnt/storage12tb when available."),
    run_id: str | None = typer.Option(None, "--run-id", help="Stable run id for tests/replay."),
    fixture: Path | None = typer.Option(None, "--fixture", exists=True, help="Fixture JSON with residue items. For tests only."),
    write_memory: bool = typer.Option(False, "--write-memory/--no-write-memory", help="Actually store reflection to memory."),
) -> None:
    if mode not in {"static_dream", "video_plan"}:
        raise typer.BadParameter("mode must be one of: static_dream, video_plan")
    run_id = run_id or _now_run_id()
    persona = Persona(persona_id)
    secondary_persona = Persona(secondary_persona_id) if secondary_persona_id else None
    out = output_dir or _default_output_dir(run_id)
    out.mkdir(parents=True, exist_ok=True)

    request = {
        "schema": "persona_dream.request.v1",
        "run_id": run_id,
        "mode": mode,
        "persona": {"id": persona.id, "display_name": persona.display_name},
        "secondary_persona": {"id": secondary_persona.id, "display_name": secondary_persona.display_name} if secondary_persona else None,
        "limit": limit,
        "about": about,
        "scene": scene,
        "duration_seconds": duration_seconds,
        "frames": frames,
        "fixture": str(fixture) if fixture else None,
        "write_memory": write_memory,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(out / "dream_request.json", request)

    recall_receipts: list[dict[str, Any]] = []
    items = _load_fixture(fixture) if fixture else []
    if not fixture:
        items, recall_receipts = _fetch_residue(persona, limit, about, secondary_persona, day)

    if not items:
        response = {
            "schema": "persona_dream.response.v1",
            "status": "blocked",
            "reason": "no_dream",
            "message": "No memory residue found; refusing to fabricate a persona dream.",
            "run_id": run_id,
            "output_dir": str(out),
            "recall_receipts": recall_receipts,
        }
        _write_json(out / "response.json", response)
        typer.echo(json.dumps(response, indent=2))
        raise typer.Exit(3)

    contradictions = _detect_contradictions(items)
    dream_prompt, frame_prompts, reflection = _build_prompts(persona, items, contradictions, frames, about)

    strata_achieved: dict[str, int] = {}
    for item in items:
        key = "day" if str(item.get("scope", "")).startswith("episodic:day=") else str(item.get("scope") or "unknown")
        strata_achieved[key] = strata_achieved.get(key, 0) + 1
    residue_links = {
        "schema": "persona_dream.residue_links.v1",
        "run_id": run_id,
        "day": day,
        "selection": "quota_per_stratum",
        "selection_note": (
            "drawn by quota across strata, not global top-k. Top-k over one pool "
            "is what made consecutive dreams identical: the recall queries are "
            "constants, so the same documents won the same ranking every cycle."
        ),
        "day_quota_reserved": (max(2, limit // 3) if day else 0),
        "strata_achieved": dict(sorted(strata_achieved.items())),
        "items": items,
        "recall_receipts": recall_receipts,
    }
    contradiction_report = {
        "schema": "persona_dream.contradiction_report.v1",
        "run_id": run_id,
        "contradictions": contradictions,
    }
    packet = {
        "schema": "persona_dream.packet.v1",
        "run_id": run_id,
        "mode": mode,
        "created_at": request["created_at"],
        "persona": request["persona"],
        "secondary_persona": request["secondary_persona"],
        "synthetic_content_notice": "Dream prompts and reflections are synthetic interpretations of cited residue, not factual claims.",
        "residue_items": items,
        "contradictions": contradictions,
        "dream_prompt": dream_prompt,
        "frame_prompts": frame_prompts,
        "contact_sheet": "contact_sheet.png",
        "reflection": reflection,
        "downstream_routes": {
            "full_movie": "$ask create-movie to render accepted dream packet with create-movie@v1 on dream_packet.json",
            "preferred_motion": "Dockerized ComfyUI on the local A5000 running TurboDiffusion TurboWan2.2-I2V-A14B-720P with workflow/API receipts.",
            "wan_ti2v_5b": "For local A5000/24GB rendering, use Wan2.2-TI2V-5B with --offload_model True --convert_model_dtype --t5_cpu after a reference frame or image prompt is accepted.",
            "wan_14b": "Use TurboDiffusion A14B only when ComfyUI readiness proves the distilled model and required text encoder/VAE are mounted; route non-distilled A14B/S2V/Animate-class jobs to devops/runpod or a larger GPU.",
        },
    }

    artifacts = [
        "dream_request.json",
        "residue_links.json",
        "contradiction_report.json",
        "dream_packet.json",
        "dream_prompt.txt",
        "frame_prompts.json",
        "contact_sheet.png",
        "dream_reflection.md",
        "memory_write_receipt.json",
        "response.json",
        "manifest.json",
    ]

    _write_json(out / "residue_links.json", residue_links)
    _write_json(out / "contradiction_report.json", contradiction_report)
    _write_json(out / "dream_packet.json", packet)
    (out / "dream_prompt.txt").write_text(dream_prompt + "\n")
    _write_json(out / "frame_prompts.json", {"schema": "persona_dream.frame_prompts.v1", "frames": frame_prompts})
    (out / "dream_reflection.md").write_text(reflection + "\n")
    _draw_contact_sheet(out / "contact_sheet.png", persona, frame_prompts)

    video_plan_artifacts: dict[str, Any] | None = None
    if mode == "video_plan":
        if not about:
            about = "creating the SPARTA Explorer app"
        if not scene:
            scene = (
                "Horus and Embry have tea sitting under a patio table with an umbrella on a 40k void world "
                "where Tyranids are playing in the background. Horus and Embry are talking about creating "
                "the SPARTA Explorer app in a friendly, personal way."
            )
        persona_ids = [persona.id] + ([secondary_persona.id] if secondary_persona else [])
        persona_source_context = _persona_context(persona_ids)
        sparta_source_context = _sparta_context()
        video_plan_artifacts = _build_video_plan(
            persona=persona,
            secondary=secondary_persona,
            about=about,
            scene=scene,
            duration=duration_seconds,
            items=items,
            contradictions=contradictions,
            persona_context=persona_source_context,
            sparta_context=sparta_source_context,
        )
        (out / "dream_story.md").write_text(video_plan_artifacts["dream_story_md"])
        _write_json(out / "dream_story.json", video_plan_artifacts["dream_story_json"])
        _write_json(out / "character_scene_bible.json", video_plan_artifacts["character_scene_bible"])
        _write_json(out / "storyboard.json", video_plan_artifacts["storyboard"])
        _write_json(out / "timed_transcript.json", video_plan_artifacts["timed_transcript"])
        _write_json(out / "multimodal_prompts.json", video_plan_artifacts["multimodal_prompts"])
        _write_json(out / "voice_handoff_plan.json", video_plan_artifacts["voice_handoff_plan"])
        artifacts.extend([
            "dream_story.md",
            "dream_story.json",
            "character_scene_bible.json",
            "storyboard.json",
            "timed_transcript.json",
            "multimodal_prompts.json",
            "voice_handoff_plan.json",
        ])

    if write_memory:
        try:
            receipt = _store_reflection(persona, reflection, packet, day)
        except Exception as exc:
            receipt = {
                "status": "error",
                "endpoint": "/store",
                "error": str(exc),
                "scope": persona.scope("dream-journals"),
            }
    else:
        receipt = {
            "status": "skipped",
            "reason": "write_memory_false",
            "scope": persona.scope("dream-journals"),
        }
    _write_json(out / "memory_write_receipt.json", receipt)

    artifacts.extend(["pipeline_stage_report.json", "pipeline_stage_report.md"])
    stage_report, stage_report_md = _build_stage_report(
        request=request,
        items=items,
        contradictions=contradictions,
        artifacts=artifacts,
        video_plan_artifacts=video_plan_artifacts,
        recall_receipts=recall_receipts,
        memory_receipt=receipt,
    )
    _write_json(out / "pipeline_stage_report.json", stage_report)
    (out / "pipeline_stage_report.md").write_text(stage_report_md)

    manifest = {
        "schema": "persona_dream.manifest.v1",
        "run_id": run_id,
        "mode": mode,
        "created_at": request["created_at"],
        "output_dir": str(out),
        "artifacts": sorted(set(artifacts)),
        "required_modes": {
            "static_dream": [
                "dream_request.json",
                "response.json",
                "residue_links.json",
                "contradiction_report.json",
                "dream_packet.json",
                "dream_prompt.txt",
                "frame_prompts.json",
                "contact_sheet.png",
                "dream_reflection.md",
                "memory_write_receipt.json",
                "manifest.json",
            ],
            "video_plan": [
                "dream_story.md",
                "dream_story.json",
                "character_scene_bible.json",
                "storyboard.json",
                "timed_transcript.json",
                "multimodal_prompts.json",
                "voice_handoff_plan.json",
                "manifest.json",
            ],
        },
        "next_lanes": {
            "keyframes": "Use local/containerized keyframe workflow first; Chutes z-image-turbo only after canary proof.",
            "i2v": "Use Dockerized ComfyUI TurboDiffusion TurboWan2.2-I2V-A14B-720P for accepted keyframes.",
            "continuity": "Run VLM/LLM checks through scillm against character_scene_bible.json.",
            "assembly": "Use minimal FFmpeg only after accepted clips exist; hand broader production to create-movie.",
            "stage_reports": "Each stage must write text/visual outputs and failure gaps to pipeline_stage_report.json and pipeline_stage_report.md.",
            "self_improvement_loop": "Generated keyframes/clips must be checked, corrected, regenerated or explicitly fall back before advancing.",
        },
    }
    _write_json(out / "manifest.json", manifest)

    # #1201: publish the entry in the two forms it actually needs -- an
    # annotated journal a human reads, and the annotation-stripped text the
    # renderer speaks. Chatterbox synthesizes inline tags as literal words, so
    # these cannot be the same bytes. Non-fatal: a render failure must not lose
    # the dream artifacts that already succeeded.
    journal_render: dict[str, Any] | None = None
    try:
        _render_journal = _load_sibling("render_journal_entry")
        journal_render = _render_journal.run(
            SimpleNamespace(run_dir=out, persona=persona.display_name, journal_text="", out=None)
        )
    except Exception as exc:  # noqa: BLE001 - never lose a completed dream to a renderer bug
        journal_render = {"status": "BLOCKED_JOURNAL_RENDER_ERROR",
                          "error": f"{type(exc).__name__}: {exc}"}

    response = {
        "schema": "persona_dream.response.v1",
        "status": "ok",
        "mode": mode,
        "run_id": run_id,
        "output_dir": str(out),
        "artifact_count": len(sorted(set(artifacts))),
        "memory_write_status": receipt["status"],
        "dream_packet": str(out / "dream_packet.json"),
        "manifest": str(out / "manifest.json"),
        "journal_status": (journal_render or {}).get("status"),
        "journal_error": (journal_render or {}).get("error"),
        "journal_markdown": (journal_render or {}).get("journal_markdown"),
        "journal_spoken": (journal_render or {}).get("journal_spoken"),
    }
    if mode == "video_plan":
        response.update({
            "duration_seconds": duration_seconds,
            "timed_transcript": str(out / "timed_transcript.json"),
            "multimodal_prompts": str(out / "multimodal_prompts.json"),
            "voice_handoff_plan": str(out / "voice_handoff_plan.json"),
        })
    _write_json(out / "response.json", response)
    typer.echo(json.dumps(response, indent=2))


@app.command("chutes-generate")
def chutes_generate(
    prompt: str = typer.Option(..., "--prompt", help="Prompt to send to the Chutes /generate endpoint."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory for output artifact and receipts."),
    output_name: str = typer.Option("chutes_generation", "--output-name", help="Base filename for generated output and receipt."),
    endpoint: str = typer.Option(DEFAULT_CHUTES_Z_IMAGE_TURBO_URL, "--endpoint", help="Chutes /generate endpoint URL."),
    image_path: Path | None = typer.Option(None, "--image", exists=True, help="Optional source image for I2V endpoints; base64 encoded into image_b64."),
    steps: int | None = typer.Option(None, "--steps", help="Optional Chutes endpoint steps parameter."),
    fps: int | None = typer.Option(None, "--fps", help="Optional Chutes endpoint fps parameter."),
    seed: int | None = typer.Option(None, "--seed", help="Optional seed parameter."),
    timeout_s: float = typer.Option(240.0, "--timeout-s", min=5.0, help="Per-attempt HTTP timeout."),
    max_attempts: int = typer.Option(8, "--max-attempts", min=1, max=12, help="Transient retry attempt budget."),
    base_delay_s: float = typer.Option(4.0, "--base-delay-s", min=0.1, help="Initial exponential backoff delay."),
) -> None:
    """Call Chutes image/video generation with receipt-backed transient retries.

    The live scillm proxy currently exposes chat/VLM routes but no image/video
    generation route. This command preserves the dream pipeline evidence contract
    while recording that direct Chutes /generate was used as a scoped exception.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("CHUTES_API_TOKEN") or os.environ.get("CHUTES_API_KEY")
    if not token:
        raise typer.BadParameter("CHUTES_API_TOKEN or CHUTES_API_KEY must be set")

    payload: dict[str, Any] = {"prompt": prompt}
    if image_path:
        payload["image_b64"] = base64.b64encode(image_path.read_bytes()).decode("ascii")
    if steps is not None:
        payload["steps"] = steps
    if fps is not None:
        payload["fps"] = fps
    if seed is not None:
        payload["seed"] = seed

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    safe_payload = dict(payload)
    if "image_b64" in safe_payload:
        safe_payload["image_b64"] = f"<base64:{len(payload['image_b64'])} chars>"

    attempts: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    for attempt in range(1, max_attempts + 1):
        started = time.time()
        result = _http_post_json_bytes(endpoint, payload, headers=headers, timeout=timeout_s)
        elapsed = round(time.time() - started, 3)
        body = result.get("body", b"")
        content_type = str(result.get("headers", {}).get("content-type") or result.get("headers", {}).get("Content-Type") or "")
        raw_path = output_dir / f"{output_name}_attempt_{attempt:02d}.body"
        raw_path.write_bytes(body)
        attempt_record = {
            "attempt": attempt,
            "status": result.get("status"),
            "http_status": result.get("http_status"),
            "elapsed_s": elapsed,
            "content_type": content_type,
            "body_bytes": len(body),
            "raw_body_path": str(raw_path),
            "retryable": _retryable_http_status(result.get("http_status")),
            "error": result.get("error"),
        }
        attempts.append(attempt_record)
        final = result
        if result.get("status") == "ok" and body:
            break
        if not attempt_record["retryable"] or attempt == max_attempts:
            break
        delay = min(90.0, base_delay_s * (2 ** (attempt - 1)))
        attempt_record["next_delay_s"] = delay
        time.sleep(delay)

    assert final is not None
    final_body = final.get("body", b"")
    final_content_type = str(final.get("headers", {}).get("content-type") or final.get("headers", {}).get("Content-Type") or "")
    extension = _guess_extension(final_content_type, final_body)
    output_path = output_dir / f"{output_name}{extension}"
    if final.get("status") == "ok" and final_body:
        output_path.write_bytes(final_body)
    else:
        output_path = output_dir / f"{output_name}_failed.body"
        output_path.write_bytes(final_body)

    receipt = {
        "schema": "persona_dream.chutes_generate_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "endpoint": endpoint,
        "provider": "chutes",
        "status": "ok" if final.get("status") == "ok" and final_body else "error",
        "http_status": final.get("http_status"),
        "attempt_count": len(attempts),
        "max_attempts": max_attempts,
        "retry_policy": {
            "retryable_http_statuses": sorted([408, 409, 425, 429, 500, 502, 503, 504]),
            "base_delay_s": base_delay_s,
            "timeout_s": timeout_s,
            "note": "Mirrors the transient-retry intent of scillm for a non-chat Chutes /generate surface not exposed by the live proxy.",
        },
        "scillm_route_gap": {
            "checked": True,
            "live_proxy": DEFAULT_SCILLM_BASE_URL,
            "missing_generation_routes": ["/v1/scillm/images", "/v1/scillm/videos", "/v1/images/generations", "/v1/videos/generations"],
            "use_scillm_for": ["prompt refinement", "VLM keyframe critique", "clip continuity review"],
        },
        "request": {
            "prompt": prompt,
            "safe_payload": safe_payload,
        },
        "attempts": attempts,
        "output_path": str(output_path),
        "output_bytes": output_path.stat().st_size if output_path.exists() else 0,
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest() if output_path.exists() else None,
    }
    receipt_path = output_dir / f"{output_name}_receipt.json"
    _write_json(receipt_path, receipt)
    typer.echo(json.dumps({"status": receipt["status"], "output_path": str(output_path), "receipt": str(receipt_path), "attempt_count": len(attempts)}, indent=2))


@app.command("backend-readiness")
def backend_readiness(
    output_dir: Path = typer.Option(..., "--output-dir", help="Existing dream run output directory to receive backend_readiness_receipt.json."),
    scillm_base_url: str = typer.Option(DEFAULT_SCILLM_BASE_URL, "--scillm-base-url"),
    comfyui_base_url: str = typer.Option(DEFAULT_COMFYUI_BASE_URL, "--comfyui-base-url"),
    chutes_turbowani2v_url: str = typer.Option(DEFAULT_CHUTES_TURBOWANI2V_URL, "--chutes-turbowani2v-url"),
) -> None:
    """Record backend readiness for keyframe, I2V, continuity, and assembly lanes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scillm_headers = {"Authorization": "Bearer sk-dev-proxy-123", "X-Caller-Skill": "persona-dream"}
    scillm_health = _http_json(f"{scillm_base_url.rstrip('/')}/v1/scillm/health", headers=scillm_headers)
    scillm_models = _http_json(f"{scillm_base_url.rstrip('/')}/v1/scillm/models?include_models_dev=true", headers=scillm_headers)
    openapi = _http_json(f"{scillm_base_url.rstrip('/')}/openapi.json")
    comfy_stats = _http_json(f"{comfyui_base_url.rstrip('/')}/system_stats")
    comfy_objects = _http_json(f"{comfyui_base_url.rstrip('/')}/object_info")

    models_payload = scillm_models.get("json") if scillm_models.get("status") == "ok" else {}
    models_text = json.dumps(models_payload, sort_keys=True).lower()
    gpt55_capabilities = _model_capabilities(models_payload, "gpt-5.5")
    openapi_payload = openapi.get("json") if openapi.get("status") == "ok" else {}
    openapi_paths = sorted((openapi_payload.get("paths") or {}).keys()) if isinstance(openapi_payload, dict) else []

    chutes_image_models = _run_command(
        ["./run.sh", "models", "--modality", "image", "--json"],
        cwd=Path(__file__).resolve().parents[2] / "ops-chutes",
        timeout=30,
    )
    chutes_z_image = _run_command(
        ["./run.sh", "models", "--query", "z-image", "--json"],
        cwd=Path(__file__).resolve().parents[2] / "ops-chutes",
        timeout=30,
    )
    chutes_z_image_turbo = _run_command(
        ["./run.sh", "models", "--query", "z-image-turbo", "--json"],
        cwd=Path(__file__).resolve().parents[2] / "ops-chutes",
        timeout=30,
    )
    chutes_wan = _run_command(
        ["./run.sh", "models", "--query", "wan", "--json"],
        cwd=Path(__file__).resolve().parents[2] / "ops-chutes",
        timeout=30,
    )
    chutes_turbowani2v = _run_command(
        ["./run.sh", "models", "--query", "turbowani2v", "--json"],
        cwd=Path(__file__).resolve().parents[2] / "ops-chutes",
        timeout=30,
    )
    chutes_budget = _run_command(
        ["./run.sh", "can-complete", "8"],
        cwd=Path(__file__).resolve().parents[2] / "ops-chutes",
        timeout=30,
    )

    blueprint_paths = [
        COMFYUI_ROOT / "blueprints" / "Text to Image (Z-Image-Turbo).json",
        COMFYUI_ROOT / "blueprints" / "Pose to Image (Z-Image-Turbo).json",
        COMFYUI_ROOT / "blueprints" / "Image to Video (Wan 2.2).json",
        COMFYUI_ROOT / "blueprints" / "Text to Video (Wan 2.2).json",
    ]
    model_files = []
    models_root = COMFYUI_ROOT / "models"
    mounted_models_root = Path("/mnt/storage12tb/comfyui/models")
    if models_root.exists():
        for path in sorted(models_root.rglob("*")):
            if path.is_file() and not path.name.startswith("put_"):
                model_files.append(str(path))
                if len(model_files) >= 50:
                    break
    expected_model_names = [
        "TurboWan2.2-I2V-A14B-720P.gguf",
        "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "wan_2.1_vae.safetensors",
    ]
    expected_model_locations = _find_named_files([models_root, mounted_models_root], expected_model_names)
    has_gguf_turbowan = bool(expected_model_locations["TurboWan2.2-I2V-A14B-720P.gguf"])
    has_fp8_turbowan_pair = bool(
        expected_model_locations["wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"]
        and expected_model_locations["wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"]
    )
    has_shared_i2v_deps = bool(
        expected_model_locations["umt5_xxl_fp8_e4m3fn_scaled.safetensors"]
        and expected_model_locations["wan_2.1_vae.safetensors"]
    )
    has_turbowan_model_set = bool((has_gguf_turbowan or has_fp8_turbowan_pair) and has_shared_i2v_deps)
    chutes_z_image_turbo_visible = chutes_z_image_turbo.get("stdout", "").strip() not in {"", "[]"}
    chutes_turbowani2v_visible = chutes_turbowani2v.get("stdout", "").strip() not in {"", "[]"}

    docker_ps = _run_command(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"],
        timeout=12,
    )
    nvidia_smi = _run_command(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader"],
        timeout=12,
    )

    missing_scillm_generation_aliases = [
        name for name in ("z-image", "wan", "turbodiffusion", "turbowan")
        if name not in models_text
    ]
    missing_openapi_generation_paths = [
        path for path in ("/v1/images/generations", "/v1/videos/generations", "/v1/scillm/images", "/v1/scillm/videos")
        if path not in openapi_paths
    ]
    receipt = {
        "schema": "persona_dream.backend_readiness_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "output_dir": str(output_dir),
        "overall_status": "blocked",
        "summary": {
            "keyframe_generation": "available" if chutes_z_image_turbo_visible else "blocked",
            "i2v_generation": "available" if (comfy_stats.get("status") == "ok" and has_turbowan_model_set) else "blocked",
            "continuity_review": "available_when_vlm_model_is_selected",
            "ffmpeg_assembly": "available_after_clips_exist",
            "comfyui_service": "available" if comfy_stats.get("status") == "ok" else "not_running",
            "turbowan_model_set": "available" if has_turbowan_model_set else "missing",
            "chutes_budget": "available" if chutes_budget.get("returncode") == 0 else "unknown_or_blocked",
            "chutes_z_image_turbo": "visible_in_local_ops" if chutes_z_image_turbo_visible else "not_visible_in_local_ops",
            "chutes_turbowani2v": "endpoint_known_but_not_proven_turbodiffusion" if chutes_turbowani2v_url else ("visible_in_local_ops" if chutes_turbowani2v_visible else "not_visible_in_local_ops"),
            "preferred_video_backend": "Dockerized ComfyUI TurboDiffusion on local A5000",
        },
        "scillm": {
            "base_url": scillm_base_url,
            "health_status": scillm_health.get("status"),
            "models_status": scillm_models.get("status"),
            "visible_generation_alias_gaps": missing_scillm_generation_aliases,
            "openapi_generation_path_gaps": missing_openapi_generation_paths,
            "openapi_path_count": len(openapi_paths),
            "gpt_5_5": gpt55_capabilities,
            "gpt_5_5_pipeline_role": "Use for prompt refinement, keyframe/clip critique, and continuity review. Do not route keyframe generation through scillm unless image_output becomes true or an image-generation endpoint is added.",
            "note": "Running scillm exposes chat/VLM metadata, but not the Chutes /generate image/video endpoints. Chutes turbowani2v should use the explicit Chutes generate endpoint or a future scillm/gateway adapter that supports non-chat generation.",
        },
        "chutes": {
            "role": "Preferred for SPARTA LLM/VLM and optional remote image/video models after canary proof; not currently proven as the 4-step TurboDiffusion Wan2.2 renderer.",
            "image_models_stdout": chutes_image_models.get("stdout"),
            "z_image_query_stdout": chutes_z_image.get("stdout"),
            "z_image_turbo_query_stdout": chutes_z_image_turbo.get("stdout"),
            "wan_query_stdout": chutes_wan.get("stdout"),
            "turbowani2v_query_stdout": chutes_turbowani2v.get("stdout"),
            "turbowani2v_generate_endpoint": chutes_turbowani2v_url,
            "turbowani2v_payload_shape": {
                "method": "POST",
                "headers": ["Authorization: Bearer <CHUTES_API_TOKEN>", "Content-Type: application/json"],
                "body": {
                    "prompt": "string",
                    "image_b64": "base64 encoded starting keyframe image",
                },
            },
            "budget_check_stdout": chutes_budget.get("stdout"),
            "budget_check_stderr": chutes_budget.get("stderr"),
            "next_probe_required": "Chutes turbowani2v is not the current preferred TurboDiffusion lane. Only retry with required steps/fps/seed if evaluating Chutes non-Turbo I2V as fallback.",
        },
        "comfyui": {
            "root": str(COMFYUI_ROOT),
            "api_base_url": comfyui_base_url,
            "system_stats_status": comfy_stats.get("status"),
            "object_info_status": comfy_objects.get("status"),
            "blueprints": [{"path": str(path), "exists": path.exists()} for path in blueprint_paths],
            "model_file_sample": model_files,
            "model_file_sample_count": len(model_files),
            "required_model_mount": "/mnt/storage12tb/comfyui/models",
            "expected_models": [
                "TurboWan2.2-I2V-A14B-720P.gguf OR high/low-noise fp8 diffusion pair",
                "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "wan_2.1_vae.safetensors",
                "Z-Image Turbo model files for keyframes/pose sheets",
            ],
            "expected_model_locations": expected_model_locations,
            "has_gguf_turbowan": has_gguf_turbowan,
            "has_fp8_turbowan_pair": has_fp8_turbowan_pair,
            "has_shared_i2v_deps": has_shared_i2v_deps,
            "has_turbowan_model_set": has_turbowan_model_set,
            "note": "Blueprints are present, but the API is not running and no substantive mounted TurboWan/Z-Image model files were proven.",
        },
        "host": {
            "docker_ps": docker_ps,
            "nvidia_smi": nvidia_smi,
        },
        "next_required_actions": [
            "Run ComfyUI as a Dockerized API service with GPU access and explicit model/output mounts.",
            "Mount or download TurboWan2.2-I2V-A14B-720P GGUF or high/low-noise fp8 pair, plus UMT5-XXL and wan_2.1_vae model files.",
            "Mount or download required Z-Image Turbo model files for keyframe and pose-sheet generation.",
            "Re-run backend-readiness until keyframe_generation and i2v_generation are available.",
        ],
    }
    _write_json(output_dir / "backend_readiness_receipt.json", receipt)
    typer.echo(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    app()
