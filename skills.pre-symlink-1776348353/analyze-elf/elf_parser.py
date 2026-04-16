"""Low-level ELF parsing and runtime detection.

Extracts headers, sections, symbols, shared libs, and detects the
embedded runtime (Bun SEA, Node SEA, Go, Rust, Zig).  Also carves
bundled JS source from .rodata for downstream AST analysis.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from loguru import logger

RUNTIME_SIGNATURES = {
    "bun_sea": {
        "strings": [b"BUN_1.", b"$bunfs/root/", b"bun-profile"],
        "label": "Bun Single-Executable Application",
    },
    "node_sea": {
        "strings": [b"NODE_SEA_FUSE", b"node::sea::"],
        "label": "Node.js Single-Executable Application",
    },
    "go": {
        "strings": [b"runtime.main", b"go.buildid"],
        "label": "Go compiled binary",
    },
    "rust": {
        "strings": [b"rust_begin_unwind", b".rustc"],
        "label": "Rust compiled binary",
    },
    "zig": {
        "strings": [b'std.debug.', b'@"zig"'],
        "label": "Zig compiled binary",
    },
}


@dataclass
class ELFAnalysis:
    """Accumulated ELF analysis results."""

    path: str = ""
    file_size: int = 0
    arch: str = ""
    bits: int = 0
    endian: str = ""
    abi: str = ""
    elf_type: str = ""
    entry_point: int = 0
    interpreter: str = ""
    sections: list[dict] = field(default_factory=list)
    symbols: list[dict] = field(default_factory=list)
    shared_libs: list[str] = field(default_factory=list)
    runtime: str = "unknown"
    runtime_label: str = "Unknown"
    bundled_assets: list[str] = field(default_factory=list)
    symbol_namespaces: dict[str, int] = field(default_factory=dict)


def run_cmd(cmd: list[str], timeout: int = 30) -> str:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(f"Command failed: {cmd[0]}: {exc}")
        return ""


def parse_elf(path: str) -> ELFAnalysis:
    """Parse ELF header, sections, and symbols."""
    analysis = ELFAnalysis(path=path)
    analysis.file_size = Path(path).stat().st_size

    with open(path, "rb") as f:
        elf = ELFFile(f)
        h = elf.header
        analysis.arch = h["e_machine"]
        analysis.bits = elf.elfclass
        analysis.endian = "little" if elf.little_endian else "big"
        analysis.abi = h["e_ident"]["EI_OSABI"]
        analysis.elf_type = h["e_type"]
        analysis.entry_point = h["e_entry"]

        for seg in elf.iter_segments():
            if seg.header["p_type"] == "PT_INTERP":
                analysis.interpreter = seg.get_interp_name()

        for section in elf.iter_sections():
            analysis.sections.append({
                "name": section.name,
                "type": section.header["sh_type"],
                "size": section.header["sh_size"],
            })

        for section in elf.iter_sections():
            if isinstance(section, SymbolTableSection):
                for sym in section.iter_symbols():
                    if sym.name:
                        analysis.symbols.append({
                            "name": sym.name,
                            "type": sym.entry["st_info"]["type"],
                            "bind": sym.entry["st_info"]["bind"],
                        })

    return analysis


def detect_runtime(path: str, analysis: ELFAnalysis) -> None:
    """Detect the runtime/compiler from binary content signatures."""
    try:
        with open(path, "rb") as f:
            content = f.read(50 * 1024 * 1024)  # Cap at 50MB
    except OSError:
        return

    for runtime_id, sig in RUNTIME_SIGNATURES.items():
        matches = sum(1 for s in sig["strings"] if s in content)
        if matches >= 2 or (matches == 1 and len(sig["strings"]) == 1):
            analysis.runtime = runtime_id
            analysis.runtime_label = sig["label"]
            break

    if analysis.runtime == "bun_sea":
        pattern = rb'\$bunfs/root/([a-z0-9_.-]+\.asset)'
        analysis.bundled_assets = sorted(set(
            m.decode() for m in re.findall(pattern, content)
        ))


def detect_shared_libs(path: str, analysis: ELFAnalysis) -> None:
    """Extract shared library dependencies via readelf."""
    output = run_cmd(["readelf", "-d", path])
    for line in output.splitlines():
        m = re.search(r"Shared library: \[(.+?)\]", line)
        if m:
            analysis.shared_libs.append(m.group(1))


def group_symbol_namespaces(analysis: ELFAnalysis) -> dict[str, int]:
    """Group symbols by C++/Rust namespace or library prefix."""
    ns: Counter = Counter()
    for sym in analysis.symbols:
        name = sym["name"]
        m = re.match(r"_ZN(\d+)(.+)", name)
        if m:
            length = int(m.group(1))
            ns[m.group(2)[:length]] += 1
        elif name.startswith("napi_"):
            ns["napi"] += 1
        elif name.startswith("uv_"):
            ns["libuv"] += 1
        elif name.startswith("node_api_"):
            ns["node_api"] += 1
    analysis.symbol_namespaces = dict(ns.most_common(20))
    return analysis.symbol_namespaces


def extract_strings(path: str, pattern: str, min_len: int = 6) -> list[str]:
    """Extract printable strings matching a regex pattern."""
    output = run_cmd(["strings", f"-n{min_len}", path], timeout=60)
    regex = re.compile(pattern, re.IGNORECASE)
    return [line for line in output.splitlines() if regex.search(line)]


def extract_statements(path: str, pattern: str) -> list[str]:
    """Extract semicolon-delimited statements matching a regex pattern.

    Unlike extract_strings which returns whole lines, this splits on
    semicolons first — critical for bundled JS where a single line
    can be 10K+ chars containing hundreds of statements.
    """
    output = run_cmd(["strings", "-n10", path], timeout=120)
    regex = re.compile(pattern, re.IGNORECASE)
    results = []
    seen: set[str] = set()
    for line in output.splitlines():
        for fragment in line.split(";"):
            clean = fragment.strip()
            if len(clean) > 15 and clean not in seen and regex.search(clean):
                seen.add(clean)
                results.append(clean)
    return results


def carve_js_source(path: str) -> str:
    """Carve embedded JS asset files from a Bun SEA binary.

    Bun SEA binaries contain two types of JS:
    1. Main bundle (minified, single block) — hard to parse
    2. Asset files ($bunfs/root/*.asset) — original readable source
       with imports, JSDoc, proper formatting

    This function extracts the ASSET files, which are already readable
    and can be parsed by /treesitter without beautification.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        logger.warning(f"Failed to read binary: {exc}")
        return ""

    # Find all $bunfs/root/*.asset entries — readable source files
    # Format: /$bunfs/root/name.asset\x00<JS source with \x0a newlines>
    asset_pattern = rb'/\$bunfs/root/([\w.-]+\.asset)\x00'
    assets: list[tuple[str, str]] = []

    for m in re.finditer(asset_pattern, data):
        name = m.group(1).decode("ascii", errors="replace")
        # Source starts right after the null terminator
        start = m.end()
        end = start
        while end < len(data) and end - start < 500_000:
            byte = data[end]
            if 32 <= byte <= 126 or byte in (9, 10, 13):
                end += 1
            else:
                break
        content = data[start:end].decode("ascii", errors="replace").strip()
        if len(content) > 100:
            assets.append((name, content))

    if assets:
        logger.info(f"Carved {len(assets)} readable JS asset files from bunfs")
        parts = []
        for name, content in assets:
            parts.append(f"// === {name} ===\n{content}")
        return "\n\n".join(parts)

    # Fallback: extract the main bundle (minified) if no assets found
    # Find the largest contiguous printable text block
    logger.info("No bunfs assets found — extracting largest text block")
    blocks = []
    current: list[int] = []
    for byte in data:
        if 32 <= byte <= 126 or byte in (9, 10, 13):
            current.append(byte)
        else:
            if len(current) > 10_000:
                blocks.append(bytes(current).decode("ascii", errors="replace"))
            current = []

    if blocks:
        blocks.sort(key=len, reverse=True)
        result = blocks[0][:2_000_000]  # Cap at 2MB
        logger.info(f"Extracted main bundle: {len(result):,} chars")
        return result

    return ""


def beautify_js(source: str) -> str:
    """Beautify minified JS source for readable AST analysis.

    Adds newlines, indentation, and structure so /treesitter can parse
    it and the LLM can read it.
    """
    import jsbeautifier

    opts = jsbeautifier.default_options()
    opts.indent_size = 2
    opts.max_preserve_newlines = 2
    opts.wrap_line_length = 120

    result = jsbeautifier.beautify(source, opts)
    logger.info(f"Beautified {len(source)} chars → {len(result)} chars "
                f"({len(result.splitlines())} lines)")
    return result
