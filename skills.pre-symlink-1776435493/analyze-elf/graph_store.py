"""Store extracted binary features to ArangoDB via memory daemon Unix socket.

Creates graph nodes (namespaces, methods, events, schemas, state machines,
parameters, CLI commands) and edges (contains, payload, emits, triggers,
has_parameter) for multi-hop traversal in the Binary Explorer.

NO graph_memory imports. Uses httpx with Unix socket transport to hit
the memory daemon's /upsert endpoint.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import httpx
from loguru import logger

from elf_parser import ELFAnalysis
from feature_extractor import FeatureInventory

MEMORY_SOCK = "/run/user/1000/embry/memory.sock"
FEATURES_COLL = "binary_features"
EDGES_COLL = "binary_feature_edges"


def _client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCK)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=30)


def _upsert(client: httpx.Client, collection: str, documents: list[dict]) -> int:
    """Upsert documents, return count of inserted+updated."""
    if not documents:
        return 0
    resp = client.post("/upsert", json={"collection": collection, "documents": documents})
    resp.raise_for_status()
    data = resp.json()
    return data.get("inserted", 0) + data.get("updated", 0)


def _key(binary: str, *parts: str) -> str:
    """Generate a stable _key from binary name + parts."""
    raw = f"{binary}:{':'.join(parts)}"
    return re.sub(r"[^a-zA-Z0-9_:.-]", "_", raw)[:250]


def _infer_namespace(method_name: str) -> str:
    """Extract namespace from dotted method name."""
    if "." in method_name:
        return method_name.split(".")[0]
    return "unknown"


def _infer_cluster(namespace: str, name: str) -> str:
    """Map a feature to its visual cluster."""
    ns = namespace.lower()
    n = name.lower()
    if ns == "droid":
        return "droid"
    if ns == "daemon":
        return "daemon"
    if ns == "tunnel":
        return "tunnel"
    if "mcp" in n:
        return "mcp"
    if "mission" in n or "worker" in n:
        return "mission"
    if "terminal" in n:
        return "terminal"
    return ns or "other"


def store_graph(
    binary_name: str,
    analysis: ELFAnalysis,
    inventory: FeatureInventory,
    treesitter_symbols: list[dict] | None = None,
) -> dict:
    """Store extracted features as graph nodes + edges in ArangoDB.

    Returns summary of what was stored.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    param_nodes: dict[str, dict] = {}  # deduped parameter nodes

    # ── Namespace nodes (the "forest" view) ──
    namespaces = set()
    for m in inventory.jsonrpc_methods:
        method = m.get("method", m) if isinstance(m, dict) else m
        ns = _infer_namespace(method)
        namespaces.add(ns)

    for ns in namespaces:
        nodes.append({
            "_key": _key(binary_name, "ns", ns),
            "binary_name": binary_name,
            "node_type": "namespace",
            "name": ns,
            "label": f"{ns}.* namespace",
            "namespace": ns,
            "cluster": _infer_cluster(ns, ns),
            "extraction_tier": "T0",
            "confidence": 1.0,
        })

    # ── CLI command nodes ──
    for cmd in inventory.cli_commands:
        name = cmd.get("name", "") if isinstance(cmd, dict) else cmd
        desc = cmd.get("description", "") if isinstance(cmd, dict) else ""
        nodes.append({
            "_key": _key(binary_name, "cli", name),
            "binary_name": binary_name,
            "node_type": "cli_command",
            "name": name,
            "label": name,
            "description": desc,
            "namespace": "cli",
            "cluster": "cli",
            "extraction_tier": "T0",
            "confidence": 1.0,
        })

    # ── RPC method nodes ──
    for m in inventory.jsonrpc_methods:
        method = m.get("method", m) if isinstance(m, dict) else m
        ns = _infer_namespace(method)
        short = method.split(".")[-1] if "." in method else method
        cluster = _infer_cluster(ns, method)

        nodes.append({
            "_key": _key(binary_name, "rpc", method),
            "binary_name": binary_name,
            "node_type": "rpc",
            "name": method,
            "label": short,
            "namespace": ns,
            "cluster": cluster,
            "extraction_tier": "T0",
            "confidence": 1.0,
        })

        # Edge: namespace contains method
        edges.append({
            "_key": _key(binary_name, "edge", "contains", ns, method),
            "_from": f"{FEATURES_COLL}/{_key(binary_name, 'ns', ns)}",
            "_to": f"{FEATURES_COLL}/{_key(binary_name, 'rpc', method)}",
            "binary_name": binary_name,
            "edge_type": "contains",
        })

    # ── Event type nodes ──
    for evt in inventory.event_types:
        etype = evt.get("type", evt) if isinstance(evt, dict) else evt
        prefix = etype.split("_")[0]
        cluster = _infer_cluster("", etype)

        nodes.append({
            "_key": _key(binary_name, "event", etype),
            "binary_name": binary_name,
            "node_type": "event",
            "name": etype,
            "label": etype,
            "namespace": prefix,
            "cluster": cluster,
            "extraction_tier": "T0",
            "confidence": 1.0,
        })

    # ── Schema nodes ──
    for schema in inventory.zod_schemas:
        if not isinstance(schema, dict):
            continue
        name = schema.get("name", "unknown")
        fields = schema.get("fields", [])
        # Preserve field type info for AST tab display (name: type pairs)
        typed_fields = [
            {"name": f.get("name", f) if isinstance(f, dict) else str(f),
             "type": f.get("type", "unknown") if isinstance(f, dict) else "unknown"}
            for f in fields
        ]
        field_names = [f["name"] for f in typed_fields]

        nodes.append({
            "_key": _key(binary_name, "schema", name),
            "binary_name": binary_name,
            "node_type": "schema",
            "name": name,
            "label": name,
            "namespace": "schema",
            "cluster": "schema",
            "fields": field_names,
            "typed_fields": typed_fields,
            "extraction_tier": "T0",
            "confidence": 1.0,
        })

        # Create parameter nodes from schema fields
        for fname in field_names:
            if fname and len(fname) > 2:
                pkey = _key(binary_name, "param", fname)
                if pkey not in param_nodes:
                    param_nodes[pkey] = {
                        "_key": pkey,
                        "binary_name": binary_name,
                        "node_type": "parameter",
                        "name": fname,
                        "label": fname,
                        "namespace": "param",
                        "cluster": "param",
                        "extraction_tier": "T0",
                        "confidence": 1.0,
                        "sources": ["schema"],
                    }
                elif "schema" not in param_nodes[pkey].get("sources", []):
                    param_nodes[pkey]["sources"].append("schema")

                # Edge: schema has_parameter
                edges.append({
                    "_key": _key(binary_name, "edge", "has_param", name, fname),
                    "_from": f"{FEATURES_COLL}/{_key(binary_name, 'schema', name)}",
                    "_to": f"{FEATURES_COLL}/{pkey}",
                    "binary_name": binary_name,
                    "edge_type": "has_parameter",
                    "shared_field": fname,
                })

    # ── State machine nodes ──
    for sm in inventory.state_machines:
        if not isinstance(sm, dict):
            continue
        enum_name = sm.get("enum_name", "unknown")
        states = sm.get("states", [])
        state_values = [
            s.get("value", s) if isinstance(s, dict) else str(s)
            for s in states
        ]

        nodes.append({
            "_key": _key(binary_name, "fsm", enum_name),
            "binary_name": binary_name,
            "node_type": "state_machine",
            "name": enum_name,
            "label": enum_name,
            "namespace": "fsm",
            "cluster": _infer_cluster("", " ".join(state_values)),
            "states": state_values,
            "extraction_tier": "T0",
            "confidence": 1.0,
        })

    # ── Treesitter parameter nodes (from function signatures) ──
    if treesitter_symbols:
        for sym in treesitter_symbols:
            sig = sym.get("signature", "")
            name = sym.get("name", "")
            if not sig:
                continue
            # Extract parameter names from signatures like "function foo(a, b, c)"
            paren_match = re.search(r"\(([^)]*)\)", sig)
            if paren_match:
                params_str = paren_match.group(1)
                for param in params_str.split(","):
                    param = param.strip().split(":")[0].split("=")[0].strip()
                    param = re.sub(r"[^a-zA-Z0-9_]", "", param)
                    if param and len(param) > 2 and param not in ("undefined", "null", "true", "false"):
                        pkey = _key(binary_name, "param", param)
                        if pkey not in param_nodes:
                            param_nodes[pkey] = {
                                "_key": pkey,
                                "binary_name": binary_name,
                                "node_type": "parameter",
                                "name": param,
                                "label": param,
                                "namespace": "param",
                                "cluster": "param",
                                "extraction_tier": "T1",
                                "confidence": 0.8,
                                "sources": ["treesitter"],
                            }
                        elif "treesitter" not in param_nodes[pkey].get("sources", []):
                            param_nodes[pkey]["sources"].append("treesitter")
                            # Upgrade tier if both sources found
                            param_nodes[pkey]["confidence"] = 1.0

    # Add deduplicated parameter nodes
    nodes.extend(param_nodes.values())

    # ── Infer edges: method → schema (shared field names) ──
    schema_field_map: dict[str, list[str]] = {}  # field → [schema_keys]
    for schema in inventory.zod_schemas:
        if not isinstance(schema, dict):
            continue
        name = schema.get("name", "unknown")
        for f in schema.get("fields", []):
            fname = f.get("name", f) if isinstance(f, dict) else str(f)
            schema_field_map.setdefault(fname, []).append(name)

    # Key fields that indicate method→schema relationships
    key_fields = {"sessionId", "automationId", "terminalId", "missionId", "serverId"}
    for m in inventory.jsonrpc_methods:
        method = m.get("method", m) if isinstance(m, dict) else m
        method_lower = method.lower()

        for field, schema_names in schema_field_map.items():
            if field.lower() in method_lower or any(
                kw in method_lower for kw in [field.lower().replace("id", "")]
            ):
                for sname in schema_names:
                    edges.append({
                        "_key": _key(binary_name, "edge", "payload", method, sname),
                        "_from": f"{FEATURES_COLL}/{_key(binary_name, 'rpc', method)}",
                        "_to": f"{FEATURES_COLL}/{_key(binary_name, 'schema', sname)}",
                        "binary_name": binary_name,
                        "edge_type": "payload",
                        "shared_field": field,
                    })

    # ── Infer edges: method → event (same prefix heuristic) ──
    for m in inventory.jsonrpc_methods:
        method = m.get("method", m) if isinstance(m, dict) else m
        method_short = method.split(".")[-1] if "." in method else method

        for evt in inventory.event_types:
            etype = evt.get("type", evt) if isinstance(evt, dict) else evt
            # Match if method name contains event prefix or vice versa
            evt_prefix = etype.split("_")[0]
            if evt_prefix in method_short.lower() and evt_prefix not in ("error", "session"):
                edges.append({
                    "_key": _key(binary_name, "edge", "emits", method, etype),
                    "_from": f"{FEATURES_COLL}/{_key(binary_name, 'rpc', method)}",
                    "_to": f"{FEATURES_COLL}/{_key(binary_name, 'event', etype)}",
                    "binary_name": binary_name,
                    "edge_type": "emits",
                })

    # ── Infer edges: event → state_machine (prefix match) ──
    for evt in inventory.event_types:
        etype = evt.get("type", evt) if isinstance(evt, dict) else evt
        evt_prefix = etype.split("_")[0]

        for sm in inventory.state_machines:
            if not isinstance(sm, dict):
                continue
            states = sm.get("states", [])
            state_values = [
                s.get("value", s) if isinstance(s, dict) else str(s)
                for s in states
            ]
            # Event prefix matches any state value prefix
            if any(evt_prefix in sv for sv in state_values):
                edges.append({
                    "_key": _key(binary_name, "edge", "triggers", etype, sm["enum_name"]),
                    "_from": f"{FEATURES_COLL}/{_key(binary_name, 'event', etype)}",
                    "_to": f"{FEATURES_COLL}/{_key(binary_name, 'fsm', sm['enum_name'])}",
                    "binary_name": binary_name,
                    "edge_type": "triggers",
                })

    # ── Infer edges: parameter → method (parameter appears in method context) ──
    for pkey, pnode in param_nodes.items():
        pname = pnode["name"]
        if pname not in key_fields:
            continue
        for m in inventory.jsonrpc_methods:
            method = m.get("method", m) if isinstance(m, dict) else m
            # Check if this key field likely belongs to this method's namespace
            method_lower = method.lower()
            pname_stem = pname.lower().replace("id", "")
            if pname_stem and pname_stem in method_lower:
                edges.append({
                    "_key": _key(binary_name, "edge", "uses_param", method, pname),
                    "_from": f"{FEATURES_COLL}/{_key(binary_name, 'rpc', method)}",
                    "_to": f"{FEATURES_COLL}/{pkey}",
                    "binary_name": binary_name,
                    "edge_type": "has_parameter",
                    "shared_field": pname,
                })

    # ── String reference nodes ──
    str_ref_keys: list[str] = []  # for edge matching
    for sref in inventory.string_references[:200]:
        val = sref.get("value", "")
        cat = sref.get("category", "unknown")
        vhash = hashlib.md5(val.encode()).hexdigest()[:12]
        skey = _key(binary_name, "string", vhash)
        str_ref_keys.append(skey)
        nodes.append({
            "_key": skey,
            "binary_name": binary_name,
            "node_type": "string_ref",
            "label": val[:60],
            "value": val,
            "category": cat,
            "usage_count": sref.get("usage_count", 1),
            "cluster": "strings",
            "extraction_tier": "T0",
            "confidence": 0.9,
        })

    # ── Edges: rpc/event → string_ref (value appears in name) ──
    for sref, skey in zip(inventory.string_references[:200], str_ref_keys):
        val_lower = sref.get("value", "").lower()
        for m in inventory.jsonrpc_methods:
            method = m.get("method", m) if isinstance(m, dict) else m
            if val_lower in method.lower() or method.lower().split(".")[-1] in val_lower:
                edges.append({
                    "_key": _key(binary_name, "edge", "references", method, skey[-12:]),
                    "_from": f"{FEATURES_COLL}/{_key(binary_name, 'rpc', method)}",
                    "_to": f"{FEATURES_COLL}/{skey}",
                    "binary_name": binary_name,
                    "edge_type": "references",
                })
        for evt in inventory.event_types:
            etype = evt.get("type", evt) if isinstance(evt, dict) else evt
            if val_lower in etype.lower() or etype.lower() in val_lower:
                edges.append({
                    "_key": _key(binary_name, "edge", "references", etype, skey[-12:]),
                    "_from": f"{FEATURES_COLL}/{_key(binary_name, 'event', etype)}",
                    "_to": f"{FEATURES_COLL}/{skey}",
                    "binary_name": binary_name,
                    "edge_type": "references",
                })

    # ── Cross-reference edges (calls): function → function ──
    # Build lookup of all node keys for rpc, cli_command, event, data_model
    node_name_to_key: dict[str, str] = {}
    for n in nodes:
        nt = n.get("node_type", "")
        if nt in ("rpc", "cli_command", "event"):
            name = n.get("name", n.get("label", ""))
            if name:
                node_name_to_key[name.lower()] = n["_key"]
                # Also index the short name (after last dot)
                short = name.rsplit(".", 1)[-1]
                if short and short != name:
                    node_name_to_key[short.lower()] = n["_key"]

    # Infer calls from data_models (treesitter functions that reference other functions)
    for model in inventory.data_models:
        caller_name = model.get("name", "")
        if not caller_name:
            continue
        caller_lower = caller_name.lower()
        # Check if this function name matches a known node
        caller_key = node_name_to_key.get(caller_lower)
        if not caller_key:
            continue
        # Check signature for references to other known functions
        sig = model.get("signature", "")
        for known_name, known_key in node_name_to_key.items():
            if known_key == caller_key:
                continue
            if known_name in sig.lower() or known_name in caller_lower:
                continue  # skip self-references and substring matches of own name
            # Check if the known function name appears in the model's code context
            if known_name in (model.get("body", "") or "").lower():
                edges.append({
                    "_key": _key(binary_name, "edge", "calls", caller_name, known_name),
                    "_from": f"{FEATURES_COLL}/{caller_key}",
                    "_to": f"{FEATURES_COLL}/{known_key}",
                    "binary_name": binary_name,
                    "edge_type": "calls",
                })

    # ── Import/export nodes ──
    for imp in inventory.imports[:500]:
        ikey = _key(binary_name, "import", imp["name"])
        nodes.append({
            "_key": ikey,
            "binary_name": binary_name,
            "node_type": "import",
            "label": imp["name"],
            "name": imp["name"],
            "symbol_type": imp.get("symbol_type", ""),
            "library": imp.get("library", ""),
            "cluster": "imports",
            "extraction_tier": "T0",
            "confidence": 1.0,
        })
    for exp in inventory.exports[:500]:
        ekey = _key(binary_name, "export", exp["name"])
        nodes.append({
            "_key": ekey,
            "binary_name": binary_name,
            "node_type": "export",
            "label": exp["name"],
            "name": exp["name"],
            "symbol_type": exp.get("symbol_type", ""),
            "cluster": "exports",
            "extraction_tier": "T0",
            "confidence": 1.0,
        })

    # ── Store to ArangoDB (batch in chunks of 100) ──
    try:
        client = _client()
        n_nodes = 0
        for i in range(0, len(nodes), 100):
            n_nodes += _upsert(client, FEATURES_COLL, nodes[i:i + 100])
        n_edges = 0
        for i in range(0, len(edges), 100):
            n_edges += _upsert(client, EDGES_COLL, edges[i:i + 100])
        client.close()

        summary = {
            "binary_name": binary_name,
            "nodes_stored": n_nodes,
            "edges_stored": n_edges,
            "node_counts": {
                "namespace": sum(1 for n in nodes if n["node_type"] == "namespace"),
                "cli_command": sum(1 for n in nodes if n["node_type"] == "cli_command"),
                "rpc": sum(1 for n in nodes if n["node_type"] == "rpc"),
                "event": sum(1 for n in nodes if n["node_type"] == "event"),
                "schema": sum(1 for n in nodes if n["node_type"] == "schema"),
                "state_machine": sum(1 for n in nodes if n["node_type"] == "state_machine"),
                "parameter": sum(1 for n in nodes if n["node_type"] == "parameter"),
                "string_ref": sum(1 for n in nodes if n["node_type"] == "string_ref"),
                "import": sum(1 for n in nodes if n["node_type"] == "import"),
                "export": sum(1 for n in nodes if n["node_type"] == "export"),
            },
        }
        logger.info(
            f"Stored {n_nodes} nodes + {n_edges} edges for {binary_name}: "
            f"{summary['node_counts']}"
        )
        return summary

    except Exception as exc:
        logger.error(f"Failed to store graph for {binary_name}: {exc}")
        return {"error": str(exc)}
