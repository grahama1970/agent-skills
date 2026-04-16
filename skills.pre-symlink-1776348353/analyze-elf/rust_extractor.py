"""Rust binary feature extraction.

Extracts features from compiled Rust ELF binaries by parsing:
- Demangled symbol names from .symtab/.dynsym
- Clap CLI structure from embedded help strings
- Struct/enum names from type metadata strings
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

from loguru import logger

from elf_parser import run_cmd


@dataclass
class RustFeatures:
    """Features extracted from a Rust binary."""

    functions: list[str] = field(default_factory=list)
    crates: list[str] = field(default_factory=list)
    clap_commands: list[dict] = field(default_factory=list)
    structs: list[str] = field(default_factory=list)
    enums: list[str] = field(default_factory=list)


def is_rust_binary(path: str) -> bool:
    """Detect if an ELF binary was compiled with Rust."""
    # Check via strings command (handles full binary, not just header)
    output = run_cmd(["strings", "-n10", path], timeout=30)
    return (
        "rust_begin_unwind" in output
        or "rust_panic" in output
        or "clap_builder" in output
        or "clap_derive" in output
        or ".rustc" in output
    )


def extract_rust_symbols(path: str) -> tuple[list[str], list[str]]:
    """Extract demangled Rust function names and crate names.

    Uses nm --demangle to recover readable symbol names from the
    Rust v0 mangling scheme.
    """
    output = run_cmd(["nm", "--demangle", "--defined-only", path], timeout=30)
    if not output:
        # Try dynamic symbols for stripped binaries
        output = run_cmd(["nm", "--demangle", "--dynamic", path], timeout=30)

    functions = []
    crates = set()
    seen = set()

    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name = parts[-1]
        if name in seen or len(name) > 200:
            continue
        seen.add(name)

        # Filter out stdlib and low-level symbols
        if any(name.startswith(prefix) for prefix in [
            "std::", "core::", "alloc::", "compiler_builtins::",
            "_ZN", "__rust", "rust_begin", "rust_panic",
            "DW.", ".L", "_GLOBAL",
        ]):
            continue

        functions.append(name)

        # Extract crate name (first :: segment)
        if "::" in name:
            crate = name.split("::")[0]
            if crate and len(crate) < 50 and crate[0].isalpha():
                crates.add(crate)

    return functions[:500], sorted(crates)[:100]


def extract_clap_commands(path: str) -> list[dict]:
    """Extract Clap CLI commands from embedded help text.

    Clap generates static help strings with predictable patterns:
    USAGE:, OPTIONS:, COMMANDS:, ARGS:
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []

    # Check for Clap markers
    clap_markers = [b"USAGE:", b"clap::", b"clap_builder", b"clap_derive"]
    has_clap = any(marker in data for marker in clap_markers)
    if not has_clap:
        return []

    logger.info("Detected Clap CLI framework")

    commands = []
    seen = set()

    # Clap generates help blocks with commands listed as:
    #   command_name   Description text
    # Under a "Commands:" or "Subcommands:" header
    help_pattern = re.compile(
        rb'\n\s{2,6}([\w][\w-]{1,30})\s{2,}([A-Z][\x20-\x7e]{5,80})'
    )
    for m in help_pattern.finditer(data):
        name = m.group(1).decode("ascii", errors="replace")
        desc = m.group(2).decode("ascii", errors="replace").strip()
        if name not in seen and name.islower() and not name.startswith("--"):
            seen.add(name)
            commands.append({"name": name, "description": desc})

    return commands


def extract_rust_types(path: str) -> tuple[list[str], list[str]]:
    """Extract struct and enum names from Rust binary strings.

    Rust embeds type names in panic messages, debug formatting,
    and serde serialization code.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return [], []

    structs = set()
    enums = set()

    # Struct names appear in patterns like:
    #   crate::module::StructName
    #   called `Result::unwrap()` on an `Err` value: StructName
    struct_pattern = re.compile(
        rb'(\w+::(?:\w+::)*[A-Z]\w+)(?:\s|<|\(|,|\x00)'
    )
    for m in struct_pattern.finditer(data):
        name = m.group(1).decode("ascii", errors="replace")
        if "::" in name and len(name) < 100:
            parts = name.split("::")
            type_name = parts[-1]
            if type_name[0].isupper() and len(type_name) > 2:
                # Heuristic: types with common suffixes
                if any(type_name.endswith(s) for s in [
                    "Config", "Options", "Args", "Command", "State",
                    "Error", "Result", "Builder", "Client", "Server",
                    "Handler", "Manager", "Service", "Request", "Response",
                ]):
                    structs.add(name)
                elif any(type_name.endswith(s) for s in [
                    "Kind", "Type", "Mode", "Status", "Level", "Action",
                ]):
                    enums.add(name)

    return sorted(structs)[:100], sorted(enums)[:50]


def extract_all(path: str) -> RustFeatures:
    """Extract all features from a Rust binary."""
    features = RustFeatures()

    if not is_rust_binary(path):
        return features

    logger.info("Rust binary detected — extracting Rust-specific features")

    functions, crates = extract_rust_symbols(path)
    features.functions = functions
    features.crates = crates
    logger.info(f"Rust: {len(functions)} functions, {len(crates)} crates")

    features.clap_commands = extract_clap_commands(path)
    if features.clap_commands:
        logger.info(f"Rust Clap: {len(features.clap_commands)} commands")

    structs, enums = extract_rust_types(path)
    features.structs = structs
    features.enums = enums
    if structs or enums:
        logger.info(f"Rust types: {len(structs)} structs, {len(enums)} enums")

    return features
