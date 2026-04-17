"""Batch embed images from datalake_chunks using vLLM Python API.

Three-phase pipeline:
  Phase 1: Pre-resolve all paths (existing PNGs, renderable PDFs, blocked)
  Phase 2: Render missing images from source PDFs via PyMuPDF (fitz)
  Phase 3: Batch embed all available images, upsert via /memory

All ArangoDB access via /memory daemon /list and /upsert. Zero AQL.
All rendered images saved to /mnt/storage12tb/extractor_corpus/rendered_regions/.

Usage:
    /tmp/vllm_batch_venv/bin/python .pi/skills/embedding/batch_embed_images.py --batch-size 64
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from tqdm import tqdm
from PIL import Image


# ── Config ──────────────────────────────────────────────────────────

RENDERED_BASE = Path("/mnt/storage12tb/extractor_corpus/rendered_regions")
EXTRACTED_RUNS = Path("/home/graham/workspace/experiments/pi-mono/.pi/skills/review-pdf/extracted_runs")
MEMORY_SOCK = "/run/user/1000/embry/memory.sock"


# ── Memory daemon ───────────────────────────────────────────────────

def _mem() -> httpx.Client:
    return httpx.Client(
        transport=httpx.HTTPTransport(uds=MEMORY_SOCK),
        base_url="http://localhost",
        timeout=30.0,
    )


def _list(client, filters, limit=500, offset=0, fields=None):
    payload = {"collection": "datalake_chunks", "filters": filters, "limit": limit, "offset": offset}
    if fields:
        payload["return_fields"] = fields
    r = client.post("/list", json=payload, timeout=60.0)
    r.raise_for_status()
    return r.json()


def _list_docs(client, limit=500, offset=0):
    r = client.post("/list", json={
        "collection": "datalake_docs", "limit": limit, "offset": offset,
        "return_fields": ["_key", "source", "path"],
    }, timeout=60.0)
    r.raise_for_status()
    return r.json()


def _upsert(client, docs):
    r = client.post("/upsert", json={"collection": "datalake_chunks", "documents": docs}, timeout=60.0)
    r.raise_for_status()
    return r.json()


# ── Path resolution ─────────────────────────────────────────────────

def _build_caches(mem) -> tuple:
    """Build doc_id→output_dir and doc_id→source_pdf caches."""
    path_cache = {}
    pdf_cache = {}
    offset = 0
    while True:
        data = _list_docs(mem, limit=500, offset=offset)
        for doc in data["documents"]:
            key = doc["_key"]
            if doc.get("path"):
                path_cache[key] = doc["path"]
            src = doc.get("source", "")
            if src and "/" in src and src.endswith(".pdf"):
                pdf_cache[key] = src
        if offset + data["count"] >= data["total"]:
            break
        offset += data["count"]
    return path_cache, pdf_cache


def _resolve_existing_image(doc: dict, path_cache: dict) -> Optional[str]:
    """Find existing PNG on disk from source_meta.image_path."""
    sm = doc.get("source_meta", {})
    rel = sm.get("image_path")
    if not rel:
        return None
    out_dir = path_cache.get(doc.get("doc_id"))
    if out_dir:
        p = Path(out_dir) / rel
        if p.exists():
            return str(p)
    src = doc.get("source", "")
    if src:
        p = EXTRACTED_RUNS / src / rel
        if p.exists():
            return str(p)
    return None


def _render_region(pdf_path: str, page_num: int, bbox: list, doc_key: str, asset_type: str) -> Optional[str]:
    """Render a region from a PDF page using PyMuPDF. Returns saved PNG path."""
    import fitz

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None

    if page_num >= len(doc):
        doc.close()
        return None

    page = doc[page_num]
    # bbox is [x0, y0, x1, y1] in PDF coordinates
    x0, y0, x1, y1 = bbox
    clip = fitz.Rect(x0, y0, x1, y1)

    # Render at 2x for quality
    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    doc.close()

    if pix.width < 2 or pix.height < 2:
        return None

    # Save to 12TB
    out_dir = RENDERED_BASE / doc_key
    out_dir.mkdir(parents=True, exist_ok=True)

    bbox_str = f"{int(x0)}-{int(y0)}-{int(x1)}-{int(y1)}"
    at = (asset_type or "unknown").lower().replace(" ", "_")
    filename = f"p{page_num:04d}_{bbox_str}_{at}.png"
    out_path = out_dir / filename

    pix.save(str(out_path))
    return str(out_path)


def _find_source_pdf(doc: dict, pdf_cache: dict) -> Optional[str]:
    """Find the source PDF for a chunk's parent doc."""
    doc_id = doc.get("doc_id")
    if not doc_id:
        return None

    # Direct PDF path from parent doc
    pdf_path = pdf_cache.get(doc_id)
    if pdf_path and Path(pdf_path).exists():
        return pdf_path

    # Try source field on chunk itself
    src = doc.get("source", "")
    if src and Path(src).exists() and src.endswith(".pdf"):
        return src

    return None


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--gpu-memory", type=float, default=0.65)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-render", action="store_true", help="Skip fitz rendering, only embed existing PNGs")
    args = parser.parse_args()

    mem = _mem()
    try:
        mem.get("/health").raise_for_status()
        print("[batch] Memory daemon OK", flush=True)
    except Exception as e:
        print(f"[batch] Memory daemon unreachable: {e}", flush=True)
        return

    RENDERED_BASE.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Pre-resolve all paths ──────────────────────────
    print("[batch] Phase 1: Building caches...", flush=True)
    path_cache, pdf_cache = _build_caches(mem)
    print(f"[batch] Cached {len(path_cache)} output dirs, {len(pdf_cache)} PDF paths", flush=True)

    asset_types = ["Table", "Figure"]
    all_work = []  # (doc, image_path, needs_render)

    for at in asset_types:
        data = _list(mem, {"asset_type": at, "embedding_visual": None}, limit=1)
        total = data["total"]
        print(f"[batch] {at}: {total} pending", flush=True)

        if total == 0:
            continue

        offset = 0
        pbar = tqdm(total=total, desc=f"  resolve {at}")
        while offset < total:
            fetch = min(500, total - offset)
            data = _list(mem, {"asset_type": at, "embedding_visual": None}, limit=fetch, offset=offset,
                         fields=["_key", "doc_id", "source", "source_meta", "asset_type"])
            docs = data["documents"]
            if not docs:
                break

            for doc in docs:
                sm = doc.get("source_meta", {})
                bbox = sm.get("bbox")
                page = sm.get("page")

                # Try existing image first
                img_path = _resolve_existing_image(doc, path_cache)
                if img_path:
                    all_work.append((doc, img_path, False))
                elif bbox and page is not None and not args.skip_render:
                    # Can render from PDF
                    pdf = _find_source_pdf(doc, pdf_cache)
                    if pdf:
                        all_work.append((doc, pdf, True))  # needs_render
                # else: blocked, skip

                pbar.update(1)

            offset += len(docs)
        pbar.close()

    existing = sum(1 for _, _, r in all_work if not r)
    renderable = sum(1 for _, _, r in all_work if r)
    print(f"\n[batch] Phase 1 complete:", flush=True)
    print(f"  Existing PNGs: {existing}", flush=True)
    print(f"  Renderable:    {renderable}", flush=True)
    print(f"  Total work:    {len(all_work)}", flush=True)

    if args.limit:
        all_work = all_work[:args.limit]
        print(f"  Limited to:    {len(all_work)}", flush=True)

    if args.dry_run:
        for doc, path, needs_render in all_work[:10]:
            tag = "RENDER" if needs_render else "EXISTS"
            print(f"  [{tag}] {path[:80]}", flush=True)
        return

    # ── Phase 2: Render missing images ──────────────────────────
    if renderable > 0:
        print(f"\n[batch] Phase 2: Rendering {renderable} regions from PDFs...", flush=True)
        rendered = 0
        render_failed = 0
        pbar = tqdm(total=renderable, desc="  render")

        for i, (doc, pdf_path, needs_render) in enumerate(all_work):
            if not needs_render:
                continue

            sm = doc.get("source_meta", {})
            img_path = _render_region(
                pdf_path,
                sm["page"],
                sm["bbox"],
                doc.get("doc_id", doc["_key"]),
                doc.get("asset_type", "unknown"),
            )

            if img_path:
                # Update work item with rendered path
                all_work[i] = (doc, img_path, False)
                rendered += 1
            else:
                # Mark as failed — remove from work
                all_work[i] = (doc, None, False)
                render_failed += 1

            pbar.update(1)

        pbar.close()
        print(f"[batch] Phase 2: {rendered} rendered, {render_failed} failed", flush=True)

        # Remove failed renders
        all_work = [(d, p, r) for d, p, r in all_work if p is not None]

    # ── Phase 3: Batch embed ────────────────────────────────────
    if not all_work:
        print("[batch] Nothing to embed.", flush=True)
        return

    print(f"\n[batch] Phase 3: Embedding {len(all_work)} images...", flush=True)
    from vllm import LLM, PoolingParams, EngineArgs

    engine_args = EngineArgs(
        model="Qwen/Qwen3-VL-Embedding-2B",
        runner="pooling",
        dtype="bfloat16",
        trust_remote_code=True,
        max_model_len=2048,
        gpu_memory_utilization=args.gpu_memory,
        enable_mm_embeds=True,
        enforce_eager=True,
        limit_mm_per_prompt={"image": 1, "video": 0},
        disable_log_stats=True,
    )
    llm = LLM(**vars(engine_args))
    pooling_params = PoolingParams()
    print("[batch] Model loaded.", flush=True)

    def _prepare(path: str):
        conv = [
            {"role": "system", "content": [{"type": "text", "text": "Represent this document image for retrieval."}]},
            {"role": "user", "content": [{"type": "image", "image": f"file://{os.path.abspath(path)}"}]},
        ]
        prompt = llm.llm_engine.tokenizer.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
        img = Image.open(path).convert("RGB")
        if max(img.size) > 448:
            img.thumbnail((448, 448), Image.LANCZOS)
        return {"prompt": prompt, "multi_modal_data": {"image": img}}

    embedded = 0
    skipped = 0
    errors = 0
    t_start = time.time()
    pbar = tqdm(total=len(all_work), desc="  embed")
    idx = 0

    while idx < len(all_work):
        # Build batch
        batch_docs = []
        batch_inputs = []
        batch_paths = []

        while len(batch_inputs) < args.batch_size and idx < len(all_work):
            doc, img_path, _ = all_work[idx]
            idx += 1

            try:
                img = Image.open(img_path).convert("RGB")
                w, h = img.size
                if max(w, h) / max(min(w, h), 1) > 100:
                    skipped += 1
                    pbar.update(1)
                    continue
                inp = _prepare(img_path)
                batch_inputs.append(inp)
                batch_docs.append(doc)
                batch_paths.append(img_path)
            except Exception as e:
                print(f"  [err] prepare {img_path}: {e}", flush=True)
                errors += 1
                pbar.update(1)

        if not batch_inputs:
            continue

        try:
            t0 = time.time()
            outputs = llm.embed(batch_inputs, pooling_params=pooling_params)
            bt = time.time() - t0

            upsert_docs = []
            for doc, out, img_path in zip(batch_docs, outputs, batch_paths):
                vec = out.outputs.embedding
                if not vec:
                    skipped += 1
                    pbar.update(1)
                    continue

                arr = np.array(vec, dtype=np.float32)
                norm = np.linalg.norm(arr)
                if norm > 0:
                    vec = (arr / norm).tolist()

                update = {"_key": doc["_key"], "embedding_visual": vec}
                # If this was a rendered image, also update source_meta.image_path
                if str(RENDERED_BASE) in img_path:
                    sm = doc.get("source_meta", {})
                    sm["image_path"] = img_path
                    update["source_meta"] = sm

                upsert_docs.append(update)

            if upsert_docs:
                result = _upsert(mem, upsert_docs)
                embedded += result.get("inserted", 0) + result.get("updated", 0)
                errors += len(result.get("errors", []))

            for _ in batch_docs:
                pbar.update(1)

            elapsed = time.time() - t_start
            rate = embedded / elapsed if elapsed > 0 else 0
            rem = len(all_work) - idx
            eta = rem / rate if rate > 0 else 0
            print(f"  batch {len(batch_inputs)}: {bt:.1f}s ({len(batch_inputs)/bt:.0f} img/s) | "
                  f"total: {embedded}/{len(all_work)} @ {rate:.1f} img/s | ETA: {eta/3600:.1f}h | "
                  f"skip={skipped} err={errors}", flush=True)

        except Exception as e:
            print(f"  [warn] batch failed ({e}), one-at-a-time fallback...", flush=True)
            for doc, inp, img_path in zip(batch_docs, batch_inputs, batch_paths):
                try:
                    out = llm.embed([inp], pooling_params=pooling_params)[0]
                    vec = out.outputs.embedding
                    if vec:
                        arr = np.array(vec, dtype=np.float32)
                        norm = np.linalg.norm(arr)
                        if norm > 0:
                            vec = (arr / norm).tolist()
                        update = {"_key": doc["_key"], "embedding_visual": vec}
                        if str(RENDERED_BASE) in img_path:
                            sm = doc.get("source_meta", {})
                            sm["image_path"] = img_path
                            update["source_meta"] = sm
                        _upsert(mem, [update])
                        embedded += 1
                    else:
                        skipped += 1
                except Exception:
                    errors += 1
                pbar.update(1)

    pbar.close()
    elapsed = time.time() - t_start
    print(f"\n[batch] Done in {elapsed:.0f}s: {embedded} embedded, {skipped} skipped, {errors} errors", flush=True)
    if embedded > 0:
        print(f"[batch] Average: {embedded/elapsed:.1f} img/s", flush=True)


if __name__ == "__main__":
    main()
