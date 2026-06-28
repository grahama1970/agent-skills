"""Feature extraction from ELF binaries via AST analysis.

Extracts CLI commands, Zod schemas, state machines, JSON-RPC methods,
and data models from bundled JS/TS source recovered from .rodata.
Delegates AST parsing to /treesitter.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

SKILL_DIR = Path(__file__).parent
TREESITTER_SKILL = SKILL_DIR.parent / "treesitter"


@dataclass
class FeatureInventory:
    """Extracted features from a binary."""

    cli_commands: list[dict] = field(default_factory=list)
    cli_flags: list[dict] = field(default_factory=list)
    state_machines: list[dict] = field(default_factory=list)
    zod_schemas: list[dict] = field(default_factory=list)
    jsonrpc_methods: list[dict] = field(default_factory=list)
    event_types: list[dict] = field(default_factory=list)
    data_models: list[dict] = field(default_factory=list)
    npm_packages: list[str] = field(default_factory=list)
    api_routes: list[str] = field(default_factory=list)
    string_references: list[dict] = field(default_factory=list)
    imports: list[dict] = field(default_factory=list)
    exports: list[dict] = field(default_factory=list)


def run_treesitter(code: str, language: str = "javascript") -> list[dict]:
    """Parse code via /treesitter and return symbol list."""
    run_sh = TREESITTER_SKILL / "run.sh"
    if not run_sh.exists():
        logger.warning(f"treesitter skill not found at {run_sh}")
        return []

    env = {**subprocess.os.environ, "VIRTUAL_ENV": ""}
    try:
        result = subprocess.run(
            [str(run_sh), "parse", "--language", language, "--code", code, "--content"],
            capture_output=True, text=True, timeout=60, env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        logger.warning(f"treesitter parse failed: {exc}")
    return []


def extract_cli_commands(raw_strings: list[str]) -> list[dict]:
    """Extract CLI commands from i18n translation objects.

    Droid (and similar tools) store command metadata in i18n objects:
      exec:{description:"Execute a single command",...}
      daemon:{description:"Run the Factory daemon server",...}
    """
    commands = []
    seen = set()

    # i18n command descriptions: name:{description:"..."} or
    # name:{...description:"..."}
    i18n_cmd = re.compile(
        r'(\w+):\{[^}]*?description:\s*["\']([A-Z][^"\']{10,80})["\']'
    )

    # Commander.js .command() calls: .command("name", "description")
    commander_cmd = re.compile(
        r'\.command\(\s*["\'](\w[\w-]*)["\']'
    )

    for line in raw_strings:
        for m in i18n_cmd.finditer(line):
            name = m.group(1)
            desc = m.group(2)
            # Filter out UI/framework noise
            if name not in seen and name.islower() and len(name) > 2:
                if not any(kw in name for kw in [
                    "error", "warning", "label", "title", "button",
                    "modal", "dialog", "tooltip", "placeholder",
                ]):
                    seen.add(name)
                    commands.append({"name": name, "description": desc})

        for m in commander_cmd.finditer(line):
            name = m.group(1)
            if name not in seen and name.islower():
                seen.add(name)
                commands.append({"name": name, "description": ""})

    return commands


def extract_enum_state_machines(raw_strings: list[str]) -> list[dict]:
    """Extract state machine enums from JS source strings.

    Looks for patterns like:
      M.StateName="state_value"
      M["StateName"]="state_value"
    """
    machines: dict[str, list[str]] = {}
    enum_pattern = re.compile(
        r'([A-Z]\w*)\.(\w+)\s*=\s*["\']([a-z_]+)["\']'
    )

    for line in raw_strings:
        for m in enum_pattern.finditer(line):
            var_name, key, value = m.group(1), m.group(2), m.group(3)
            machines.setdefault(var_name, []).append({
                "key": key, "value": value,
            })

    # Filter: must have 3+ underscore values AND no CSS/UI noise
    ui_noise = {
        "inline", "pinned", "expanded", "compact", "light", "dark",
        "transparent", "none", "white", "inherit", "div", "error",
        "title", "swatch", "true", "false", "object", "array",
        "string", "text", "binary", "cpp", "buttons", "component",
        "integer", "stdio", "http", "github", "unified",
    }
    results = []
    for name, states in machines.items():
        clean = [s for s in states if s["value"] not in ui_noise]
        underscore_clean = [s for s in clean if "_" in s["value"]]
        if len(underscore_clean) >= 2:
            results.append({"enum_name": name, "states": clean})

    return results


def extract_zod_schemas(raw_strings: list[str]) -> list[dict]:
    """Extract Zod schema definitions from bundled JS strings.

    Looks for patterns like:
      varName=KH.object({field:KH.string(),...})
      Jd.extend({type:KH.literal("event_name"),...})
    """
    schemas = []
    # Named schema assignments
    schema_pattern = re.compile(
        r'(\w+)\s*=\s*(?:KH|z|zod)\.object\(\{([^}]{10,500})\}\)'
    )
    # Literal type extensions (event types)
    extend_pattern = re.compile(
        r'(\w+)\s*=\s*\w+\.extend\(\{type:\s*(?:KH|z)\.literal\(["\'](\w+)["\']\)'
    )

    for line in raw_strings:
        for m in schema_pattern.finditer(line):
            name, body = m.group(1), m.group(2)
            fields = _parse_zod_fields(body)
            if fields:
                schemas.append({"name": name, "fields": fields})

        for m in extend_pattern.finditer(line):
            name, event_type = m.group(1), m.group(2)
            schemas.append({
                "name": name,
                "event_type": event_type,
                "kind": "extend",
            })

    return schemas


def _parse_zod_fields(body: str) -> list[dict]:
    """Parse Zod field definitions from a schema body string."""
    fields = []
    field_pattern = re.compile(
        r'(\w+)\s*:\s*(?:KH|z)\.(\w+)\(([^)]*)\)'
    )
    for m in field_pattern.finditer(body):
        name, zod_type, args = m.group(1), m.group(2), m.group(3)
        field_info: dict = {"name": name, "type": zod_type}
        # Extract literal values
        lit_match = re.search(r'["\']([^"\']+)["\']', args)
        if lit_match:
            field_info["value"] = lit_match.group(1)
        fields.append(field_info)
    return fields


def extract_jsonrpc_methods(raw_strings: list[str]) -> list[dict]:
    """Extract JSON-RPC method names from bundled source."""
    methods = []
    method_pattern = re.compile(
        r'method:\s*(?:KH|z)\.literal\(["\']([a-z_.]+)["\']\)'
    )
    seen = set()
    for line in raw_strings:
        for m in method_pattern.finditer(line):
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                methods.append({"method": name})
    return methods


def extract_event_types(raw_strings: list[str]) -> list[dict]:
    """Extract notification/event type literals from bundled source."""
    events = []
    event_pattern = re.compile(
        r'type:\s*(?:KH|z)\.literal\(["\'](\w+)["\']\)'
    )
    seen = set()
    for line in raw_strings:
        for m in event_pattern.finditer(line):
            event_type = m.group(1)
            if event_type not in seen:
                seen.add(event_type)
                events.append({"type": event_type})
    return events


def extract_npm_packages(raw_strings: list[str]) -> list[str]:
    """Extract npm package names from bundled package.json fragments."""
    packages = set()
    pkg_pattern = re.compile(r'"name"\s*:\s*"(@?[\w./-]+)"')
    for line in raw_strings:
        for m in pkg_pattern.finditer(line):
            name = m.group(1)
            if not name.startswith("bun-") and len(name) > 2:
                packages.add(name)
    return sorted(packages)


def extract_string_references(raw_strings: list[str]) -> list[dict]:
    """Extract high-signal string references: URLs, paths, errors, config, API routes."""
    seen: dict[str, dict] = {}  # value -> entry

    url_re = re.compile(r'https?://[^\s"\'<>]{4,200}')
    path_re = re.compile(r'(?<![a-zA-Z])(/[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+){1,10})')
    error_re = re.compile(r'["\']([^"\']{8,120}(?:error|fail|invalid|cannot|unable)[^"\']{0,80})["\']', re.IGNORECASE)
    config_re = re.compile(r'["\']([A-Z][A-Z0-9_]{2,40})[=:]')
    api_re = re.compile(r'["\'](/api/[^\s"\']{2,100})["\']')

    for line in raw_strings:
        for m in url_re.finditer(line):
            v = m.group(0).rstrip(".,;)")
            if v not in seen:
                seen[v] = {"value": v, "category": "url", "usage_count": 1}
            else:
                seen[v]["usage_count"] += 1

        for m in api_re.finditer(line):
            v = m.group(1)
            if v not in seen:
                seen[v] = {"value": v, "category": "api", "usage_count": 1}
            else:
                seen[v]["usage_count"] += 1

        for m in path_re.finditer(line):
            v = m.group(1)
            if v.startswith("/api/"):
                continue  # already caught by api_re
            if v not in seen:
                seen[v] = {"value": v, "category": "path", "usage_count": 1}
            else:
                seen[v]["usage_count"] += 1

        for m in error_re.finditer(line):
            v = m.group(1).strip()
            if v not in seen:
                seen[v] = {"value": v, "category": "error", "usage_count": 1}
            else:
                seen[v]["usage_count"] += 1

        for m in config_re.finditer(line):
            v = m.group(1)
            if v not in seen:
                seen[v] = {"value": v, "category": "config", "usage_count": 1}
            else:
                seen[v]["usage_count"] += 1

    # Sort by usage_count desc, cap at 200
    results = sorted(seen.values(), key=lambda x: x["usage_count"], reverse=True)
    return results[:200]


# Noise filter: skip compiler-internal, runtime, and single-char symbols
_SKIP_PREFIXES = ("_", ".", "__", "GCC_", "GLIBC_", "elf_", "_dl_", "_IO_", "std::")
_MIN_SYMBOL_LEN = 3


def extract_imports_exports(analysis) -> tuple[list[dict], list[dict]]:
    """Extract import/export symbols from ELF symbol table."""
    imports: list[dict] = []
    exports: list[dict] = []

    for sym in analysis.symbols:
        name = sym.get("name", "")
        bind = sym.get("bind", "")
        stype = sym.get("type", "")

        if not name or len(name) < _MIN_SYMBOL_LEN:
            continue
        if any(name.startswith(p) for p in _SKIP_PREFIXES):
            continue
        if bind != "STB_GLOBAL":
            continue

        entry = {"name": name, "symbol_type": stype}

        # UNDEF = imported from shared lib, otherwise exported
        if stype == "STT_NOTYPE" or sym.get("section", "") == "SHN_UNDEF":
            imports.append(entry)
        else:
            exports.append(entry)

    # Map imports to shared libs if available
    libs = getattr(analysis, "shared_libs", [])
    for imp in imports:
        imp["library"] = infer_import_library(imp["name"], libs)
    if libs:
        logger.info("Shared libs: {} | Imports: {} | Exports: {}", len(libs), len(imports), len(exports))

    return imports[:500], exports[:500]


def infer_import_library(symbol_name: str, shared_libs: list[str]) -> str:
    """Infer the likely shared library for a common imported ELF symbol."""
    symbol_prefixes = {
        "curl_": "libcurl",
        "dl": "libdl",
        "EVP_": "libcrypto",
        "gl": "libGL",
        "gnutls_": "libgnutls",
        "gtk_": "libgtk",
        "json_": "libjson",
        "lua_": "liblua",
        "mysql_": "libmysqlclient",
        "napi_": "libnode",
        "node_api_": "libnode",
        "pa_": "libpulse",
        "PQ": "libpq",
        "pthread_": "libpthread",
        "Py": "libpython",
        "readline": "libreadline",
        "sqlite3_": "libsqlite3",
        "SSL_": "libssl",
        "uv_": "libuv",
        "xml": "libxml2",
        "zlib": "libz",
    }

    for prefix, library_stem in symbol_prefixes.items():
        if symbol_name.startswith(prefix):
            match = next((lib for lib in shared_libs if lib.startswith(library_stem)), "")
            return match or library_stem

    if symbol_name in {"malloc", "free", "printf", "fprintf", "fopen", "fclose", "memcpy", "strlen"}:
        match = next((lib for lib in shared_libs if lib.startswith("libc.")), "")
        return match or "libc"

    return ""


def extract_api_routes(raw_strings: list[str]) -> list[str]:
    """Extract API route patterns from bundled source."""
    routes = set()
    route_pattern = re.compile(r'["\'](/(?:api|v\d+)/[\w/:.-]+)["\']')
    for line in raw_strings:
        for m in route_pattern.finditer(line):
            routes.add(m.group(1))
    return sorted(routes)


def ast_extract_classes_and_functions(js_source: str) -> list[dict]:
    """Use /treesitter to extract classes and functions from JS source.

    Breaks the source into parseable chunks and aggregates results.
    """
    symbols = []
    # treesitter parse has a practical limit; chunk the source
    chunk_size = 4000
    chunks = [
        js_source[i:i + chunk_size]
        for i in range(0, len(js_source), chunk_size)
    ]

    for i, chunk in enumerate(chunks[:50]):  # Cap at 50 chunks
        result = run_treesitter(chunk)
        for sym in result:
            sym["chunk_index"] = i
            symbols.append(sym)

    logger.info(f"treesitter extracted {len(symbols)} symbols from {len(chunks)} chunks")
    return symbols


def build_feature_inventory(
    raw_strings: list[str],
    js_source: str | None = None,
) -> FeatureInventory:
    """Build a complete feature inventory from extracted strings and JS source."""
    inv = FeatureInventory()

    inv.cli_commands = extract_cli_commands(raw_strings)
    inv.state_machines = extract_enum_state_machines(raw_strings)
    inv.zod_schemas = extract_zod_schemas(raw_strings)
    inv.jsonrpc_methods = extract_jsonrpc_methods(raw_strings)
    inv.event_types = extract_event_types(raw_strings)
    inv.npm_packages = extract_npm_packages(raw_strings)
    inv.api_routes = extract_api_routes(raw_strings)
    inv.string_references = extract_string_references(raw_strings)

    # Import/export extraction from ELF symbol table
    if analysis and hasattr(analysis, 'symbols'):
        inv.imports, inv.exports = extract_imports_exports(analysis)

    if js_source:
        inv.data_models = ast_extract_classes_and_functions(js_source)

    return inv


def format_feature_report(inv: FeatureInventory) -> str:
    """Format the feature inventory as markdown."""
    lines = ["# Feature Inventory\n"]

    if inv.cli_commands:
        lines.append(f"## CLI Commands ({len(inv.cli_commands)})\n")
        lines.append("| Command | Description |")
        lines.append("|---------|-------------|")
        for cmd in inv.cli_commands:
            lines.append(f"| `{cmd['name']}` | {cmd['description']} |")
        lines.append("")

    if inv.state_machines:
        lines.append(f"## State Machines ({len(inv.state_machines)})\n")
        for sm in inv.state_machines:
            lines.append(f"### `{sm['enum_name']}`\n")
            lines.append("```mermaid")
            lines.append("stateDiagram-v2")
            for state in sm["states"]:
                lines.append(f"    {state['value']}")
            lines.append("```\n")

    if inv.event_types:
        lines.append(f"## Event Types ({len(inv.event_types)})\n")
        # Group by prefix
        groups: dict[str, list[str]] = {}
        for evt in inv.event_types:
            prefix = evt["type"].split("_")[0]
            groups.setdefault(prefix, []).append(evt["type"])
        for prefix, types in sorted(groups.items()):
            lines.append(f"**{prefix}**: {', '.join(f'`{t}`' for t in types)}\n")

    if inv.jsonrpc_methods:
        lines.append(f"## JSON-RPC Methods ({len(inv.jsonrpc_methods)})\n")
        for m in inv.jsonrpc_methods:
            lines.append(f"- `{m['method']}`")
        lines.append("")

    if inv.zod_schemas:
        named = [s for s in inv.zod_schemas if "fields" in s]
        extends = [s for s in inv.zod_schemas if s.get("kind") == "extend"]
        if named:
            lines.append(f"## Data Schemas ({len(named)})\n")
            for s in named[:20]:
                field_list = ", ".join(f['name'] for f in s['fields'])
                lines.append(f"- **{s['name']}**: {field_list}")
            lines.append("")
        if extends:
            lines.append(f"## Schema Extensions ({len(extends)})\n")
            for s in extends:
                lines.append(f"- `{s['name']}` (type: `{s['event_type']}`)")
            lines.append("")

    if inv.npm_packages:
        lines.append(f"## Bundled Packages ({len(inv.npm_packages)})\n")
        for pkg in inv.npm_packages[:30]:
            lines.append(f"- `{pkg}`")
        lines.append("")

    if inv.api_routes:
        lines.append(f"## API Routes ({len(inv.api_routes)})\n")
        for route in inv.api_routes:
            lines.append(f"- `{route}`")
        lines.append("")

    if inv.data_models:
        classes = [s for s in inv.data_models if s.get("kind") == "class"]
        functions = [s for s in inv.data_models if s.get("kind") == "function"]
        if classes:
            lines.append(f"## Classes ({len(classes)})\n")
            for c in classes[:30]:
                lines.append(f"- `{c['name']}`")
            lines.append("")
        if functions:
            lines.append(f"## Functions ({len(functions)}, showing top 30)\n")
            for fn in functions[:30]:
                sig = fn.get("signature", fn["name"])
                if len(sig) > 80:
                    sig = sig[:77] + "..."
                lines.append(f"- `{sig}`")
            lines.append("")

    return "\n".join(lines)


def format_feature_json(inv: FeatureInventory) -> str:
    """Serialize the feature inventory to JSON."""
    return json.dumps({
        "cli_commands": inv.cli_commands,
        "state_machines": inv.state_machines,
        "event_types": inv.event_types,
        "jsonrpc_methods": inv.jsonrpc_methods,
        "zod_schemas_count": len(inv.zod_schemas),
        "npm_packages": inv.npm_packages,
        "api_routes": inv.api_routes,
        "classes_count": len([s for s in inv.data_models if s.get("kind") == "class"]),
        "functions_count": len([s for s in inv.data_models if s.get("kind") == "function"]),
        "string_references": inv.string_references,
    }, indent=2)
