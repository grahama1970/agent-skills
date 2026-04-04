"""Memory service client for automatic lesson recall and learning.

Automatically queries /memory for learned extraction parameters and
stores successful tuning results back to memory.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from loguru import logger

MEMORY_SERVICE_URL = os.environ.get("MEMORY_SERVICE_URL", "http://127.0.0.1:8601")
MEMORY_TIMEOUT = 5.0


def recall_parameters(preset: str = "", category: str = "", source: str = "") -> Optional[dict]:
    """Query /memory for learned extraction parameters.

    Returns dict with keys: flavor, line_scale, edge_tol, confidence
    or None if no relevant lessons found.
    """
    query_parts = ["table extraction"]
    if preset:
        query_parts.append(preset)
    if category:
        query_parts.append(category)
    if source:
        query_parts.append(source)
    query_parts.append("optimal parameters line_scale edge_tol")

    query = " ".join(query_parts)

    try:
        response = httpx.post(
            f"{MEMORY_SERVICE_URL}/recall",
            json={"q": query, "k": 5, "threshold": 0.5},
            timeout=MEMORY_TIMEOUT,
        )
        if response.status_code != 200:
            return None

        data = response.json()
        items = data.get("items", [])

        if not items:
            logger.debug(f"No memory lessons found for: {query}")
            return None

        # Parse parameters from the best match
        best = items[0]
        solution = best.get("solution", "") + " " + best.get("playbook", "")

        result = {"confidence": best.get("scores", {}).get("dense", 0.5)}

        # Extract flavor
        if "lattice" in solution.lower():
            result["flavor"] = "lattice"
        elif "stream" in solution.lower():
            result["flavor"] = "stream"

        # Extract line_scale
        import re
        ls_match = re.search(r"line[_\s]?scale[=:\s]+(\d+)", solution, re.IGNORECASE)
        if ls_match:
            result["line_scale"] = int(ls_match.group(1))

        # Extract edge_tol
        et_match = re.search(r"edge[_\s]?tol[=:\s]+(\d+)", solution, re.IGNORECASE)
        if et_match:
            result["edge_tol"] = int(et_match.group(1))

        if "flavor" in result or "line_scale" in result:
            logger.info(f"Memory recall for '{query}': {result}")
            return result

        return None

    except Exception as e:
        logger.debug(f"Memory recall failed: {e}")
        return None


def learn_parameters(
    preset: str,
    category: str,
    flavor: str,
    line_scale: Optional[int] = None,
    edge_tol: Optional[int] = None,
    fragmentation: int = 0,
    cell_count: int = 0,
    pdf_name: str = "",
    bridge_tags: list[str] | None = None,
) -> bool:
    """Store successful tuning parameters to /memory.

    Only stores if fragmentation == 0 (successful extraction).
    """
    if fragmentation > 0:
        logger.debug(f"Skipping memory learn: fragmentation={fragmentation} > 0")
        return False

    problem = f"Optimal table extraction for {category} {preset} PDFs"

    params = [f"flavor={flavor}"]
    if line_scale is not None:
        params.append(f"line_scale={line_scale}")
    if edge_tol is not None:
        params.append(f"edge_tol={edge_tol}")

    solution = f"Use {', '.join(params)}. Achieved 0% fragmentation with {cell_count} cells."
    if pdf_name:
        solution += f" Tested on {pdf_name}."

    tags = ["table-extraction", f"preset:{preset}", f"category:{category}"]
    if bridge_tags:
        tags.extend(bridge_tags)

    try:
        response = httpx.post(
            f"{MEMORY_SERVICE_URL}/learn",
            json={
                "problem": problem,
                "solution": solution,
                "tags": tags,
            },
            timeout=MEMORY_TIMEOUT,
        )
        if response.status_code == 200:
            logger.info(f"Stored to /memory: {problem} -> {solution}")
            return True
        else:
            logger.warning(f"Memory learn failed: {response.status_code}")
            return False

    except Exception as e:
        logger.debug(f"Memory learn failed: {e}")
        return False


def get_baseline_from_memory(preset: str = "", category: str = "") -> tuple[list[int], list[int]]:
    """Get baseline parameter grids from memory.

    If memory has learned good parameters for this preset/category,
    return a focused grid centered on those values.
    Otherwise return None to use defaults.

    Returns:
        (lattice_scales, stream_tols) or (None, None) to use defaults
    """
    params = recall_parameters(preset=preset, category=category)

    if not params:
        return None, None

    lattice_scales = None
    stream_tols = None

    if params.get("line_scale"):
        ls = params["line_scale"]
        # Build focused grid around learned value
        lattice_scales = sorted(set([
            max(5, ls - 10),
            max(5, ls - 5),
            ls,
            ls + 5,
            ls + 10,
        ]))
        logger.info(f"Using memory-guided lattice grid: {lattice_scales}")

    if params.get("edge_tol"):
        et = params["edge_tol"]
        stream_tols = sorted(set([
            max(10, et - 25),
            et,
            et + 25,
            et + 50,
        ]))
        logger.info(f"Using memory-guided stream grid: {stream_tols}")

    return lattice_scales, stream_tols
