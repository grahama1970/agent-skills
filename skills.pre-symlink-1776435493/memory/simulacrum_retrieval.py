"""QRA retrieval functions for the Brandon Simulacrum.

Provides hybrid search across ArangoDB SPARTA QRAs, Brandon's personal library,
and graph-expanded results via subgraph traversal. All retrieval is done via
subprocess calls to the memory venv to avoid dependency contamination.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

# Memory integration - Brandon's personal library (books, papers, talks, standards)
MEMORY_ROOT = Path(
    os.environ.get("MEMORY_ROOT", str(Path.home() / "workspace/experiments/memory"))
)
MEMORY_VENV_PYTHON = str(MEMORY_ROOT / ".venv" / "bin" / "python")


def expand_qras_via_subgraph(
    query_text: str,
    seed_control_ids: list[str],
    k: int = 5,
    depth: int = 2,
) -> list[dict[str, Any]]:
    """Expand QRA results using SPARTA graph traversal.

    Traverses sparta_qra_edges (shared_countermeasure/shared_technique links
    between sparta_controls) to find graph-connected controls, then retrieves
    the highest-grounding QRAs for those controls.

    Args:
        query_text: Original query for relevance scoring
        seed_control_ids: Control IDs from initial QRA hits
        k: Max additional QRAs to return
        depth: Graph traversal depth (1-2 hops)

    Returns:
        List of graph-expanded QRAs with provenance metadata
    """
    if not seed_control_ids:
        return []

    try:
        code = (
            "import sys, json, os\n"
            f"sys.path.insert(0, {str(MEMORY_ROOT / 'src')!r})\n"
            "os.environ.setdefault('ARANGO_DB', 'memory')\n"
            "from graph_memory.arango_client import get_db\n"
            "db = get_db()\n"
            f"seed_ids = {json.dumps(seed_control_ids[:5])}\n"
            f"depth = {depth}\n"
            f"k = {k}\n"
            "\n"
            "# Traverse sparta_qra_edges from seed controls\n"
            "# Map control_ids to sparta_controls document IDs\n"
            "start_vertices = [f'sparta_controls/ctrl__{cid}' for cid in seed_ids]\n"
            "\n"
            "# Graph traversal: find connected controls via shared countermeasures/techniques\n"
            "aql = f'''\n"
            "FOR start IN @starts\n"
            "  FOR v, e, p IN 1..{depth} ANY start sparta_qra_edges\n"
            "    OPTIONS {{uniqueVertices: \"global\", bfs: true}}\n"
            "    FILTER v._id NOT IN @starts\n"
            "    LET ctrl_id = SUBSTITUTE(v._key, \"ctrl__\", \"\")\n"
            "    COLLECT cid = ctrl_id INTO grp\n"
            "    LET edge = FIRST(grp)[*].e\n"
            "    RETURN {{control_id: cid, edge_type: edge.edge_type, depth: LENGTH(FIRST(grp)[*].p.edges)}}\n"
            "'''\n"
            "try:\n"
            "    neighbors = list(db.aql.execute(aql, bind_vars={\n"
            "        'starts': start_vertices,\n"
            "    }))\n"
            "except Exception as e:\n"
            "    print(json.dumps([]))\n"
            "    sys.exit(0)\n"
            "\n"
            "if not neighbors:\n"
            "    print(json.dumps([]))\n"
            "    sys.exit(0)\n"
            "\n"
            "# Get highest-grounding QRAs for each neighbor control\n"
            "neighbor_cids = [n['control_id'] for n in neighbors[:k*2]]\n"
            "edge_map = {n['control_id']: n for n in neighbors}\n"
            "qra_aql = '''\n"
            "FOR doc IN sparta_qra\n"
            "  FILTER doc.control_id IN @cids\n"
            "  FILTER doc.grounding_score >= 0.7\n"
            "  SORT doc.grounding_score DESC\n"
            "  COLLECT cid = doc.control_id INTO grp\n"
            "  LET best = FIRST(grp)\n"
            "  RETURN {\n"
            "    control_id: cid,\n"
            "    qra_id: best.doc.qra_id,\n"
            "    question: SUBSTRING(best.doc.question, 0, 300),\n"
            "    answer: SUBSTRING(best.doc.answer, 0, 500),\n"
            "    reasoning: SUBSTRING(best.doc.reasoning, 0, 300),\n"
            "    grounding_score: best.doc.grounding_score,\n"
            "    conceptual_tags: best.doc.conceptual_tags,\n"
            "    tactical_tags: best.doc.tactical_tags\n"
            "  }\n"
            "'''\n"
            "qras = list(db.aql.execute(qra_aql, bind_vars={'cids': neighbor_cids}))\n"
            "\n"
            "expanded = []\n"
            "seen = set(seed_ids)\n"
            "for qra in qras:\n"
            "    cid = qra['control_id']\n"
            "    if cid in seen:\n"
            "        continue\n"
            "    seen.add(cid)\n"
            "    edge_info = edge_map.get(cid, {})\n"
            "    expanded.append({\n"
            "        'qra_id': f'graph-{qra.get(\"qra_id\", cid)}',\n"
            "        'control_id': cid,\n"
            "        'question': qra.get('question', ''),\n"
            "        'answer': qra.get('answer', ''),\n"
            "        'reasoning': qra.get('reasoning', ''),\n"
            "        'grounding_score': round(qra.get('grounding_score', 0.5), 3),\n"
            "        'conceptual_tags': qra.get('conceptual_tags', []),\n"
            "        'tactical_tags': qra.get('tactical_tags', []),\n"
            "        '_source': 'subgraph_expansion',\n"
            "        '_graph_depth': edge_info.get('depth', 1),\n"
            "        '_edge_types': [edge_info.get('edge_type', 'related')],\n"
            "    })\n"
            "    if len(expanded) >= k:\n"
            "        break\n"
            "\n"
            "expanded.sort(key=lambda x: x['grounding_score'], reverse=True)\n"
            "print(json.dumps(expanded[:k], default=str))\n"
        )
        result = subprocess.run(
            [MEMORY_VENV_PYTHON, "-c", code],
            capture_output=True, text=True, timeout=15, cwd=str(MEMORY_ROOT),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception as e:
        logger.debug(f"Subgraph expansion failed (non-fatal): {e}")
    return []


def search_sparta_qras_arango(
    intent: dict[str, Any], limit: int = 10
) -> list[dict[str, Any]]:
    """Search SPARTA QRAs via ArangoDB hybrid search (BM25 + vector + graph).

    Replaces the deprecated DuckDB search with graph_memory's hybrid_search_sparta_qra.
    Returns QRAs from the sparta_qra ArangoDB collection.

    Args:
        intent: Intent mapper result with entities, tier1, original_query
        limit: Maximum results

    Returns:
        List of QRA dicts with grounding scores
    """
    # Build query text from intent
    query_text = intent.get("original_query", "")
    if not query_text:
        entities = intent.get("entities") or []
        tier1 = intent.get("tier1") or []
        parts = [str(p) for p in entities + tier1 if p is not None]
        query_text = " ".join(parts) if parts else "space cybersecurity"

    try:
        code = (
            "import sys, json\n"
            f"sys.path.insert(0, {str(MEMORY_ROOT / 'src')!r})\n"
            "from graph_memory.arango_client import get_db\n"
            "from graph_memory.hybrid_search import hybrid_search_sparta_qra\n"
            "db = get_db()\n"
            f"results = hybrid_search_sparta_qra(db, query={json.dumps(query_text)}, k={limit})\n"
            "print(json.dumps(results, default=str))\n"
        )
        result = subprocess.run(
            [MEMORY_VENV_PYTHON, "-c", code],
            capture_output=True, text=True, timeout=15, cwd=str(MEMORY_ROOT),
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            qras = []
            for item in data:
                qras.append({
                    "qra_id": item.get("_key", ""),
                    "control_id": item.get("control_id", ""),
                    "question": item.get("question", ""),
                    "reasoning": item.get("reasoning", ""),
                    "answer": item.get("answer", ""),
                    "citations": [],
                    "confidence": "high" if item.get("grounding_score", 0) >= 0.75 else "partial",
                    "conceptual_tags": item.get("conceptual_tags", []),
                    "tactical_tags": item.get("tactical_tags", []),
                    "grounding_score": item.get("grounding_score", 0.0),
                    "_source": "arango_hybrid",
                })
            logger.debug(f"ArangoDB hybrid search returned {len(qras)} QRAs for: {query_text[:60]}")
            return qras
    except Exception as e:
        logger.debug(f"ArangoDB SPARTA QRA search failed (non-fatal): {e}")
    return []


def query_brandon_library(
    query_text: str, k: int = 5
) -> list[dict[str, Any]]:
    """Query Brandon's personal library via graph_memory recall.

    Searches the brandon_bailey scope in ArangoDB for relevant content
    from Brandon's books, papers, talks, and standards.

    Args:
        query_text: Search query
        k: Number of results to return

    Returns:
        List of memory results converted to QRA-compatible format
    """
    try:
        code = (
            "import sys, json\n"
            f"sys.path.insert(0, {str(MEMORY_ROOT / 'src')!r})\n"
            "from graph_memory.api import MemoryClient\n"
            "client = MemoryClient(scope='brandon_bailey')\n"
            f"results = client.recall(q={json.dumps(query_text)}, scope='brandon_bailey', k={k})\n"
            "print(json.dumps(results, default=str))\n"
        )
        result = subprocess.run(
            [MEMORY_VENV_PYTHON, "-c", code],
            capture_output=True, text=True, timeout=15, cwd=str(MEMORY_ROOT),
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            qra_compat = []
            for item in data.get("results", []):
                qra_compat.append({
                    "qra_id": f"library-{item.get('_key', 'unknown')}",
                    "control_id": "LIBRARY",
                    "question": item.get("problem", ""),
                    "reasoning": "",
                    "answer": item.get("solution", ""),
                    "citations": [f"Brandon Bailey Library: {item.get('problem', '')[:80]}"],
                    "confidence": "library",
                    "conceptual_tags": item.get("tags", []),
                    "tactical_tags": [],
                    "grounding_score": min(item.get("score", 0.5) + 0.2, 1.0),
                    "_source": "brandon_library",
                })
            return qra_compat
    except Exception as e:
        logger.debug(f"Brandon library query failed (non-fatal): {e}")
    return []
