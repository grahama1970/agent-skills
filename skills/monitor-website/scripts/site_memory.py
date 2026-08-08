#!/usr/bin/env python3
"""Store and version the site's AUTHORED content in /memory (ArangoDB via the
memory daemon on :8601), and regenerate content.json from it.

Design (verified against the memory SKILL + live OpenAPI):
  * The site builds in GitHub Actions, which CANNOT reach local ArangoDB. So
    /memory is the editable SOURCE OF TRUTH for authored copy, but the deploy
    still builds from a git-committed cache (site/content.json). Flow:
        edit in /memory  ->  `pull`  ->  commit content.json  ->  CI builds.
  * /store auto-upserts by _key (latest-wins) — it is NOT versioned on its own.
    So versioning is explicit here: every `push` writes an IMMUTABLE revision
    document (site:project:<slug>:r<NNN>) in addition to upserting the mutable
    "current" document (site:project:<slug>). The revision docs ARE the version
    history in /memory; git history of content.json is the second backbone.
  * Only AUTHORED content lives here (project name/blurb/question/href). The
    generated `stats` block stays derived from the repo and is never stored.

Commands:
  push     content.json -> /memory (new revision only when content changed)
  pull     /memory -> content.json (authored projects; stats preserved)
  history  print the in-memory revision history for one slug or all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CONTENT = REPO / "site/content.json"
BASE = "http://127.0.0.1:8601"
COLLECTION = "grahama_site"              # current docs — recall-indexed (in view)
REV_COLLECTION = "grahama_site_revisions"  # immutable history — NOT indexed
AUTHORED_FIELDS = ("name", "blurb", "question", "why", "href")
# Bump when the stored doc SHAPE changes (recall fields, tags) so existing rows
# are re-stored even when the authored content_sha256 is unchanged.
# v3: revisions relocated to grahama_site_revisions; current docs carry deprecated=false.
SCHEMA_VERSION = 3


def _recall_fields(slug: str, body: dict) -> dict:
    """Standard top-level fields the memory daemon's BM25 SEARCH clause and
    Qdrant semantic sync actually index (content.* nested fields are ignored by
    both). retrieval_text is the concatenated authored prose."""
    parts = [body.get("name", ""), body.get("blurb", ""),
             body.get("question", ""), body.get("why", "")]
    return {
        "title": body.get("name", ""),
        "summary": body.get("blurb", ""),
        "text": body.get("why", ""),
        "question": body.get("question", ""),
        "retrieval_text": " — ".join(p for p in parts if p),
        "tags": ["grahama_site", "project", slug],
        "scope": "grahama-site",
    }


class MemoryError(RuntimeError):
    pass


class CollectionMissing(MemoryError):
    """The target collection does not exist yet (first run, before any /store)."""


def _post(path: str, payload: dict, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("detail", "")
        except Exception:
            pass
        if e.code == 404 and "not found" in detail.lower():
            raise CollectionMissing(detail) from e
        raise MemoryError(f"{path} -> HTTP {e.code}: {detail or e}") from e
    except urllib.error.URLError as e:
        raise MemoryError(f"memory daemon unreachable at {BASE}{path}: {e}") from e


def _health() -> None:
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
            h = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        raise MemoryError(f"memory daemon unreachable at {BASE}: {e}") from e
    if not h.get("memory_db_connected"):
        raise MemoryError(f"memory db not connected: {h}")


def _commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
    ).strip()


def _now() -> str:
    # git commit time of HEAD — deterministic, no wall-clock (matches other gens).
    return subprocess.check_output(
        ["git", "show", "-s", "--format=%cI", "HEAD"], cwd=REPO, text=True
    ).strip()


def _sha(content: dict) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _authored(project: dict) -> dict:
    return {k: project[k] for k in AUTHORED_FIELDS if k in project}


def _by_keys(keys: list[str], collection: str = COLLECTION) -> dict[str, dict]:
    if not keys:
        return {}
    try:
        res = _post("/recall/by-keys", {"collection": collection, "keys": keys})
    except CollectionMissing:
        return {}  # collection not created yet — first push seeds it via /store
    items = res.get("results") or res.get("documents") or res.get("items") or []
    return {d["_key"]: d for d in items if isinstance(d, dict) and "_key" in d}


def _store(document: dict, collection: str = COLLECTION) -> None:
    res = _post("/store", {"collection": collection, "document": document})
    if not (res.get("stored") or res.get("ok") or res.get("_key")):
        raise MemoryError(f"/store did not confirm write: {res}")


def push() -> int:
    _health()
    content = json.loads(CONTENT.read_text())
    projects = content["projects"]
    commit, as_of = _commit(), _now()

    cur_keys = [f"site:project:{p['slug']}" for p in projects]
    current = _by_keys(cur_keys)

    changed, unchanged = [], []
    for p in projects:
        slug = p["slug"]
        ckey = f"site:project:{slug}"
        body = _authored(p)
        sha = _sha(body)
        prev = current.get(ckey)
        if prev and prev.get("content_sha256") == sha and prev.get("schema_version") == SCHEMA_VERSION:
            unchanged.append(slug)
            continue
        rev = int(prev.get("rev", 0)) + 1 if prev else 1
        common = {
            "kind": "grahama_site_content",
            "section": "project",
            "slug": slug,
            "content": body,
            "content_sha256": sha,
            "schema_version": SCHEMA_VERSION,
            "rev": rev,
            "as_of": as_of,
            "source_commit": commit,
        }
        # Immutable revision snapshot -> separate NON-indexed collection (history).
        _store(
            {**common, "_key": f"site:project:{slug}:r{rev:03d}", "record": "revision"},
            collection=REV_COLLECTION,
        )
        # Mutable current pointer -> grahama_site (recall-indexed). deprecated=false
        # gives the standard soft-delete/GC tombstone field a default it can flip to.
        _store({
            **common,
            "_key": ckey,
            "record": "current",
            "deprecated": False,
            **_recall_fields(slug, body),
        })
        changed.append((slug, rev))

    # Manifest (also versioned) records the authored set + overall revision.
    man_key = "site:manifest"
    man_prev = _by_keys([man_key]).get(man_key)
    man_rev = int(man_prev.get("rev", 0)) + 1 if man_prev else 1
    if changed or not man_prev:
        man = {
            "kind": "grahama_site_manifest",
            "slugs": [p["slug"] for p in projects],
            "rev": man_rev,
            "as_of": as_of,
            "source_commit": commit,
            "record": "current",
        }
        _store({**man, "_key": f"{man_key}:r{man_rev:03d}", "record": "revision"},
               collection=REV_COLLECTION)
        _store({**man, "_key": man_key, "deprecated": False})

    # Read-back verification — never trust the write response alone.
    verify = _by_keys(cur_keys)
    for p in projects:
        ckey = f"site:project:{p['slug']}"
        got = verify.get(ckey)
        if not got or got.get("content_sha256") != _sha(_authored(p)):
            raise MemoryError(f"read-back mismatch for {ckey}")

    print(f"push: {len(changed)} changed, {len(unchanged)} unchanged -> {COLLECTION}")
    for slug, rev in changed:
        print(f"  {slug} -> r{rev:03d}")
    print(f"read-back verified {len(projects)} current docs @ {commit}")
    return 0


def pull() -> int:
    _health()
    content = json.loads(CONTENT.read_text())
    man = _by_keys(["site:manifest"]).get("site:manifest")
    if not man or not man.get("slugs"):
        raise MemoryError("no site:manifest in /memory — run `push` to seed first")
    slugs = man["slugs"]
    current = _by_keys([f"site:project:{s}" for s in slugs])
    if len(current) != len(slugs):
        missing = [s for s in slugs if f"site:project:{s}" not in current]
        raise MemoryError(f"missing current docs in /memory: {missing}")

    # Reconstruct authored projects from memory, preserving field order + slug.
    existing = {p["slug"]: p for p in content["projects"]}
    projects = []
    for slug in slugs:
        doc = current[f"site:project:{slug}"]
        merged = dict(existing.get(slug, {"slug": slug}))
        merged["slug"] = slug
        merged.update(doc["content"])
        projects.append(merged)

    content["projects"] = projects  # stats block left untouched (generated)
    CONTENT.write_text(
        json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"pull: wrote {len(projects)} authored projects from {COLLECTION} "
          f"(manifest r{man.get('rev')}) -> content.json")
    return 0


def history(slug: str | None) -> int:
    _health()
    man = _by_keys(["site:manifest"]).get("site:manifest")
    if not man:
        raise MemoryError("no site:manifest — nothing stored yet")
    slugs = [slug] if slug else man["slugs"]
    for s in slugs:
        cur = _by_keys([f"site:project:{s}"]).get(f"site:project:{s}")
        latest = int(cur.get("rev", 0)) if cur else 0
        revs = _by_keys(
            [f"site:project:{s}:r{r:03d}" for r in range(1, latest + 1)],
            collection=REV_COLLECTION,
        )
        print(f"{s}: {latest} revision(s)")
        for r in range(1, latest + 1):
            d = revs.get(f"site:project:{s}:r{r:03d}")
            if d:
                print(f"  r{r:03d} @ {d.get('source_commit')} · {d.get('as_of')} "
                      f"· sha {d.get('content_sha256', '')[:12]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Store/version site content in /memory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("push", help="content.json -> /memory (versioned)")
    sub.add_parser("pull", help="/memory -> content.json")
    h = sub.add_parser("history", help="show in-memory revision history")
    h.add_argument("--slug", default=None)
    args = ap.parse_args()
    try:
        if args.cmd == "push":
            return push()
        if args.cmd == "pull":
            return pull()
        if args.cmd == "history":
            return history(args.slug)
    except MemoryError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
