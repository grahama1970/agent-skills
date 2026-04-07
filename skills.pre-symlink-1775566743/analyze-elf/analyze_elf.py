"""Reverse-engineer features from ELF binaries.

Primary command is `features` — extracts CLI commands, state machines,
protocols, schemas, and data models from compiled binaries.  Automatically
generates a /create-walkthrough prosecution brief with Mermaid diagrams.

Low-level ELF plumbing (headers, sections, symbols) available via `elf` subcommand.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from loguru import logger

from elf_parser import (
    ELFAnalysis,
    beautify_js,
    carve_js_source,
    detect_runtime,
    detect_shared_libs,
    extract_statements,
    extract_strings,
    group_symbol_namespaces,
    parse_elf,
    run_cmd,
)
from deterministic_extractor import extract_all as deterministic_extract
from go_extractor import extract_all as go_extract, is_go_binary
from rust_extractor import extract_all as rust_extract, is_rust_binary
from feature_extractor import (
    FeatureInventory,
    build_feature_inventory,
    format_feature_json,
    format_feature_report,
    run_treesitter,
)

import subprocess

import httpx as _httpx

app = typer.Typer(help="Reverse-engineer features from ELF binaries.")
SKILL_DIR = Path(__file__).parent
SKILLS_DIR = SKILL_DIR.parent
MEMORY_URL = "http://127.0.0.1:8601"


def _recall_binary(binary_name: str) -> str:
    """Check /memory for prior analysis of this binary."""
    try:
        resp = _httpx.post(
            f"{MEMORY_URL}/recall",
            json={"q": f"analyze-elf {binary_name} features", "k": 3},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("found"):
                items = data.get("items", [])
                context = "\n".join(
                    f"- {i.get('solution', '')[:200]}" for i in items[:3]
                )
                logger.info(f"Memory recall: {len(items)} prior results for {binary_name}")
                return f"Prior analysis of {binary_name}:\n{context}"
    except Exception as exc:
        logger.debug(f"Memory recall failed: {exc}")
    return ""


def _research_binary(binary_name: str, goal: str) -> str:
    """Run /dogpile to research what this binary is."""
    dogpile_run = SKILLS_DIR / "dogpile" / "run.sh"
    if not dogpile_run.exists():
        logger.debug("dogpile skill not found")
        return ""

    query = f"{binary_name} CLI tool features documentation API"
    logger.info(f"Researching {binary_name} via /dogpile...")
    try:
        env = {**subprocess.os.environ, "VIRTUAL_ENV": ""}
        result = subprocess.run(
            [str(dogpile_run), "search", query],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if result.returncode == 0 and result.stdout:
            # Extract the synthesis section (most useful part)
            lines = result.stdout.splitlines()
            synthesis = []
            in_synthesis = False
            for line in lines:
                if "Codex Technical Overview" in line or "Synthesis" in line:
                    in_synthesis = True
                elif in_synthesis and line.startswith("## "):
                    break
                elif in_synthesis:
                    synthesis.append(line)
            context = "\n".join(synthesis[:30])
            if context:
                logger.info(f"Dogpile returned {len(context)} chars of research context")
                return context
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.debug(f"Dogpile failed: {exc}")
    return ""


def _learn_binary(
    binary_name: str, analysis: "ELFAnalysis", inv: "FeatureInventory", goal: str,
) -> None:
    """Store analysis results in /memory for future sessions."""
    cmd_names = [c["name"] for c in inv.cli_commands]
    event_count = len(inv.event_types)
    rpc_count = len(inv.jsonrpc_methods)
    schema_count = len(inv.zod_schemas)

    problem = f"Features of {binary_name} ({analysis.runtime_label})"
    solution = (
        f"CLI commands: {', '.join(cmd_names[:10])}. "
        f"{event_count} event types, {rpc_count} RPC methods, "
        f"{schema_count} schemas, {len(inv.state_machines)} state machines. "
        f"Runtime: {analysis.runtime_label}. "
        f"Goal: {goal}"
    )

    try:
        resp = _httpx.post(
            f"{MEMORY_URL}/learn",
            json={"problem": problem, "solution": solution},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Learned {binary_name} analysis to /memory")
    except Exception as exc:
        logger.debug(f"Memory learn failed: {exc}")


def _parse_help_commands(help_text: str) -> list[dict]:
    """Parse CLI commands from --help output (ground truth)."""
    import re
    commands = []
    # Commander.js format: "  command_name  Description text"
    # Lines under "Commands:" section
    in_commands = False
    for line in help_text.splitlines():
        if "Commands:" in line:
            in_commands = True
            continue
        if in_commands:
            if not line.strip():
                continue
            if line and not line.startswith(" "):
                break
            m = re.match(
                r'\s{2,}(\w[\w-]*)(?:\|[\w-]+)?\s+'
                r'(?:\[options\]\s+)?(?:\[[\w.]+\]\s+)?'
                r'(.+)',
                line,
            )
            if m:
                commands.append({
                    "name": m.group(1),
                    "description": m.group(2).strip(),
                })
    return commands


def _full_analysis(binary: str) -> tuple[ELFAnalysis, list[str]]:
    """Run ELF parse + runtime detection, return high-signal strings.

    Extracts strings in priority tiers to maximize signal-to-noise:
    1. Application help text, i18n descriptions, command definitions
    2. Zod/schema definitions, enum assignments, event types
    3. JSON-RPC methods, API routes, protocol keywords
    """
    analysis = parse_elf(binary)
    detect_runtime(binary, analysis)
    detect_shared_libs(binary, analysis)
    group_symbol_namespaces(analysis)

    # Tier 1: Application i18n descriptions and command definitions
    # These are the highest-signal strings — droid stores help text
    # in i18n translation objects, not raw --flag help blocks
    tier1 = extract_strings(binary, pattern=(
        r'description:\s*"[A-Z]|description:"[A-Z]|'
        r'\.command\(|subcommand|helpText|'
        r'Commands:|Usage:\s*\w+\s'
    ))

    # Tier 2: Schemas, enums, event types (split on semicolons first)
    tier2 = extract_statements(binary, pattern=(
        r'KH\.literal\(|KH\.object\(|KH\.nativeEnum|'
        r'\.extend\(\{type:|'
        r'\w+\.\w+\s*=\s*"[a-z_]+"'
    ))

    # Tier 3: Protocol and API surface (split on semicolons first)
    tier3 = extract_statements(binary, pattern=(
        r'jsonrpc|method:\s*KH\.literal|'
        r'droid\.\w+|factory\w*Version|'
        r'/api/|/v\d+/'
    ))

    # Deduplicate — prioritize Zod schemas and event definitions
    # Sort: KH.literal/KH.object patterns first (highest signal)
    seen = set()
    raw_zod = []
    raw_other = []
    for line in tier2 + tier3 + tier1:
        clean = line.strip()
        if clean not in seen and 10 < len(clean) < 2000:
            seen.add(clean)
            if "KH." in clean or "extend({type:" in clean:
                raw_zod.append(clean)
            else:
                raw_other.append(clean)
    raw = raw_zod + raw_other

    logger.info(f"Extracted {len(raw)} high-signal strings "
                f"(t1={len(tier1)}, t2={len(tier2)}, t3={len(tier3)})")
    return analysis, raw


def _format_walkthrough(
    analysis: ELFAnalysis,
    inv: FeatureInventory,
    goal: str,
) -> str:
    """Generate a prosecution brief walkthrough with Mermaid diagrams."""
    name = Path(analysis.path).name
    lines = [
        f"# Walkthrough: {name}",
        "",
        f"**Goal**: {goal}",
        "",
        "## Executive Summary",
        "",
        f"`{name}` is a {analysis.bits}-bit {analysis.arch} "
        f"{analysis.elf_type} binary ({analysis.file_size:,} bytes), "
        f"identified as **{analysis.runtime_label}**.",
        "",
    ]

    if analysis.shared_libs:
        lines.append(f"Links against {len(analysis.shared_libs)} shared libraries, "
                      f"imports {len(analysis.symbols)} symbols.")
    lines.append("")

    # ── CLI Commands ──
    if inv.cli_commands:
        lines.extend([
            "## CLI Commands",
            "",
            "```mermaid",
            "graph TD",
            f'    {name.upper()}["{name}"]',
        ])
        for cmd in inv.cli_commands:
            safe = cmd["name"].replace("-", "_")
            lines.append(f'    {name.upper()} --> {safe}["{cmd["name"]}"]')
        lines.extend(["```", ""])
        lines.append("| Command | Description |")
        lines.append("|---------|-------------|")
        for cmd in inv.cli_commands:
            lines.append(f"| `{cmd['name']}` | {cmd['description']} |")
        lines.append("")

    # ── State Machines ──
    if inv.state_machines:
        lines.append("## State Machines\n")
        for sm in inv.state_machines:
            lines.extend([
                f"### `{sm['enum_name']}`\n",
                "```mermaid",
                "stateDiagram-v2",
            ])
            states = [s["value"] for s in sm["states"]]
            lines.append(f"    [*] --> {states[0]}")
            for i, state in enumerate(states[:-1]):
                lines.append(f"    {state} --> {states[i + 1]}")
            lines.extend(["```", ""])

    # ── Event Types ──
    if inv.event_types:
        lines.append(f"## Event Types ({len(inv.event_types)})\n")
        groups: dict[str, list[str]] = {}
        for evt in inv.event_types:
            prefix = evt["type"].split("_")[0]
            groups.setdefault(prefix, []).append(evt["type"])

        lines.extend([
            "```mermaid",
            "graph TB",
            '    subgraph events["Event Types"]',
            "        direction TB",
        ])
        for prefix, types in sorted(groups.items()):
            lines.append(f'        subgraph {prefix}["{prefix}"]')
            for t in types:
                safe = t.replace("-", "_")
                lines.append(f'            {safe}["{t}"]')
            lines.append("        end")
        lines.extend(["    end", "```", ""])

    # ── JSON-RPC Methods ──
    if inv.jsonrpc_methods:
        lines.append(f"## JSON-RPC Methods ({len(inv.jsonrpc_methods)})\n")
        for m in inv.jsonrpc_methods:
            lines.append(f"- `{m['method']}`")
        lines.append("")

    # ── Zod Schemas ──
    named_schemas = [s for s in inv.zod_schemas if "fields" in s]
    if named_schemas:
        lines.append(f"## Data Schemas ({len(named_schemas)})\n")
        for s in named_schemas[:15]:
            lines.append(f"### `{s['name']}`\n")
            lines.append("| Field | Type |")
            lines.append("|-------|------|")
            for f in s["fields"]:
                val = f.get("value", "")
                type_str = f["type"]
                if val:
                    type_str += f' (`"{val}"`)'
                lines.append(f"| `{f['name']}` | {type_str} |")
            lines.append("")

    # ── Classes (from AST) ──
    classes = [s for s in inv.data_models if s.get("kind") == "class"]
    if classes:
        lines.append(f"## Classes ({len(classes)})\n")
        for c in classes[:20]:
            lines.append(f"- `{c['name']}`")
        lines.append("")

    # ── Bundled Packages ──
    if inv.npm_packages:
        lines.append(f"## Bundled Packages ({len(inv.npm_packages)})\n")
        for pkg in inv.npm_packages[:20]:
            lines.append(f"- `{pkg}`")
        lines.append("")

    # ── Binary Identity ──
    lines.extend([
        "## Binary Identity\n",
        f"- **Runtime**: {analysis.runtime_label}",
        f"- **Architecture**: {analysis.arch} ({analysis.bits}-bit)",
        f"- **Shared libs**: {', '.join(analysis.shared_libs) or 'none (static)'}",
        f"- **Symbols**: {len(analysis.symbols)} imported",
        "",
    ])

    # ── Risks ──
    lines.extend([
        "## What Could Go Wrong\n",
        "- Minified JS: variable names are meaningless; feature extraction relies on "
        "string literals, Zod schemas, and AST structure",
        "- Bundled library code (Bun runtime, npm deps) inflates feature counts — "
        "not all extracted items are application features",
        "- Static analysis cannot reveal env-dependent behavior",
        "",
        f"*Generated by `/analyze-elf` — source: `{analysis.path}`*",
    ])

    return "\n".join(lines)


# ── CLI Commands ──────────────────────────────────────────────────────


@app.command()
def features(
    binary: str = typer.Argument(..., help="Path to ELF binary"),
    goal: str = typer.Option(
        "extract all features", help="What you want to understand"
    ),
    output: str | None = typer.Option(None, help="Write walkthrough to file"),
    output_format: str = typer.Option("walkthrough", help="Output: walkthrough, json, summary"),
    offline: bool = typer.Option(False, "--offline", help="Skip memory/dogpile network calls"),
    store: bool = typer.Option(False, "--store", help="Store features to ArangoDB graph for Binary Explorer"),
):
    """Extract features from a binary and generate a walkthrough.

    Pipeline:
      0. /memory recall + /dogpile — research what this binary is
      1. --help parsing — CLI commands (ground truth)
      2. Deterministic extraction — known patterns
      3. Runtime-specific extraction (Go, Rust)
      4. bunfs carve → jsbeautify → /treesitter — AST from source
      5. Walkthrough generation with Mermaid diagrams
      6. /memory learn — store findings
    """
    logger.info(f"Extracting features from {binary} — goal: {goal}")
    binary_name = Path(binary).name

    # ── Step 0: Memory recall + research context ──
    prior_knowledge = _recall_binary(binary_name)
    research_context = ""
    if prior_knowledge:
        logger.info(f"Memory has prior knowledge of {binary_name}")
        research_context = prior_knowledge
    elif not offline:
        research_context = _research_binary(binary_name, goal)

    analysis, raw_strings = _full_analysis(binary)

    # ── Step 1: CLI commands from --help (ground truth) ──
    help_text = run_cmd([binary, "--help"], timeout=5)
    inv = FeatureInventory()
    if help_text:
        inv.cli_commands = _parse_help_commands(help_text)
        logger.info(f"Parsed {len(inv.cli_commands)} commands from --help")

    # ── Step 2: Deterministic extraction (Tier 0 known patterns) ──
    logger.info("Tier 0: deterministic extraction...")
    det = deterministic_extract(binary)
    inv.jsonrpc_methods = [{"method": m} for m in det.jsonrpc_methods]
    inv.event_types = [{"type": lit} for lit in det.literals]
    # Deterministic extractor gives field names only; feature_extractor
    # parses KH.type() calls to get actual types.  Merge: use typed fields
    # from feature_extractor when available, fall back to "unknown".
    from feature_extractor import extract_zod_schemas as _extract_zod_schemas
    typed_schemas = _extract_zod_schemas(raw_strings)
    # Build a lookup: schema_name -> {field_name: field_dict}
    _typed_lookup: dict[str, dict[str, dict]] = {}
    for ts in typed_schemas:
        if "fields" in ts:
            _typed_lookup[ts["name"]] = {
                f["name"]: f for f in ts["fields"]
            }
    inv.zod_schemas = []
    # Start with deterministic schemas (broader coverage)
    # det.schemas values are now list[dict] with {name, type} from KH.type() parsing
    for name, fields in det.schemas.items():
        fe_typed = _typed_lookup.get(name, {})
        merged = []
        for f in fields:
            fname = f["name"] if isinstance(f, dict) else str(f)
            ftype = f.get("type", "unknown") if isinstance(f, dict) else "unknown"
            # Prefer feature_extractor type if available (more precise)
            if fname in fe_typed:
                merged.append(fe_typed[fname])
            else:
                merged.append({"name": fname, "type": ftype})
        inv.zod_schemas.append({"name": name, "fields": merged})
    # Add any typed schemas not in the deterministic set
    det_names = set(det.schemas.keys())
    for ts in typed_schemas:
        if ts.get("name") not in det_names and "fields" in ts:
            inv.zod_schemas.append(ts)
    for enum_name, states in det.enums.items():
        inv.state_machines.append({
            "enum_name": enum_name,
            "states": [{"key": s, "value": s} for s in states],
        })
    logger.info(
        f"Tier 0: {len(inv.state_machines)} enums, "
        f"{len(inv.event_types)} literals, "
        f"{len(inv.jsonrpc_methods)} RPC methods, "
        f"{len(inv.zod_schemas)} schemas"
    )

    # ── Step 2b: Runtime-specific extraction (Go, Rust) ──
    if is_go_binary(binary):
        go_features = go_extract(binary)
        # Merge Go features into inventory
        for cmd in go_features.cobra_commands:
            if cmd["name"] not in {c["name"] for c in inv.cli_commands}:
                inv.cli_commands.append(cmd)
        for svc in go_features.protobuf_services:
            inv.jsonrpc_methods.append({"method": svc["name"], "protocol": "grpc"})
        for msg in go_features.protobuf_messages:
            inv.zod_schemas.append({
                "name": msg["name"],
                "fields": [],
                "protocol": "protobuf",
            })
        # Go functions become data_models for the walkthrough
        for fn in go_features.functions[:50]:
            inv.data_models.append({"kind": "function", "name": fn})
        logger.info(
            f"Go: {len(go_features.functions)} functions, "
            f"{len(go_features.cobra_commands)} cobra commands, "
            f"{len(go_features.protobuf_services)} grpc services"
        )

    if is_rust_binary(binary):
        rust_features = rust_extract(binary)
        for cmd in rust_features.clap_commands:
            if cmd["name"] not in {c["name"] for c in inv.cli_commands}:
                inv.cli_commands.append(cmd)
        for s in rust_features.structs:
            inv.zod_schemas.append({"name": s, "fields": [], "source": "rust"})
        for e in rust_features.enums:
            inv.state_machines.append({
                "enum_name": e,
                "states": [],
                "source": "rust",
            })
        for fn in rust_features.functions[:50]:
            inv.data_models.append({"kind": "function", "name": fn})
        logger.info(
            f"Rust: {len(rust_features.functions)} functions, "
            f"{len(rust_features.clap_commands)} clap commands, "
            f"{len(rust_features.structs)} structs, "
            f"{len(rust_features.enums)} enums"
        )

    # ── Step 3: jsbeautify → /treesitter → AST symbols ──
    logger.info("Carving + beautifying JS source...")
    js_raw = carve_js_source(binary)
    if len(js_raw) > 100:
        js_pretty = beautify_js(js_raw)
        # Treesitter on chunks of beautified JS
        ast_symbols = []
        chunk_size = 8000
        chunks = [js_pretty[i:i+chunk_size] for i in range(0, min(len(js_pretty), 200000), chunk_size)]
        for chunk in chunks:
            ast_symbols.extend(run_treesitter(chunk))
        logger.info(f"Treesitter extracted {len(ast_symbols)} symbols from {len(chunks)} chunks")

        # Add AST classes/functions to inventory
        for sym in ast_symbols:
            if sym.get("kind") in ("class", "function"):
                inv.data_models.append(sym)
    else:
        ast_symbols = []
        logger.info("No JS source found (non-JS binary)")

    if output_format == "json":
        result = format_feature_json(inv)
    elif output_format == "summary":
        result = format_feature_report(inv)
    else:
        result = _format_walkthrough(analysis, inv, goal)

    if output:
        Path(output).write_text(result)
        logger.info(f"Written to {output}")
    print(result)

    # ── Step 5b: Store to ArangoDB graph ──
    if store:
        from graph_store import store_graph
        summary = store_graph(binary_name, analysis, inv, treesitter_symbols=ast_symbols)
        logger.info(f"Stored to graph: {summary}")

    # ── Step 6: Learn to /memory ──
    if not offline:
        _learn_binary(binary_name, analysis, inv, goal)


@app.command()
def elf(
    binary: str = typer.Argument(..., help="Path to ELF binary"),
    output_format: str = typer.Option("markdown", help="Output: markdown, json"),
):
    """Low-level ELF analysis: headers, sections, symbols, shared libs."""
    analysis = parse_elf(binary)
    detect_runtime(binary, analysis)
    detect_shared_libs(binary, analysis)
    group_symbol_namespaces(analysis)

    if output_format == "json":
        data = {
            "path": analysis.path,
            "file_size": analysis.file_size,
            "arch": analysis.arch,
            "bits": analysis.bits,
            "runtime": analysis.runtime_label,
            "shared_libs": analysis.shared_libs,
            "symbols_count": len(analysis.symbols),
            "symbol_namespaces": analysis.symbol_namespaces,
        }
        print(json.dumps(data, indent=2))
    else:
        lines = [
            f"# {Path(binary).name}\n",
            f"- **Size**: {analysis.file_size:,} bytes",
            f"- **Arch**: {analysis.arch} ({analysis.bits}-bit, {analysis.endian})",
            f"- **Runtime**: {analysis.runtime_label}",
            f"- **Linker**: {analysis.interpreter or 'static'}",
            f"- **Libs**: {', '.join(analysis.shared_libs) or 'none'}",
            f"- **Symbols**: {len(analysis.symbols)}",
        ]
        if analysis.bundled_assets:
            lines.append(f"- **Bun assets**: {len(analysis.bundled_assets)}")
        print("\n".join(lines))


@app.command("strings")
def strings_cmd(
    binary: str = typer.Argument(..., help="Path to ELF binary"),
    pattern: str | None = typer.Option(None, help="Regex filter"),
    limit: int = typer.Option(100, help="Max results"),
):
    """Extract strings with optional regex filtering."""
    results = extract_strings(binary, pattern=pattern or ".")[:limit]
    for s in results:
        print(s)


if __name__ == "__main__":
    app()
