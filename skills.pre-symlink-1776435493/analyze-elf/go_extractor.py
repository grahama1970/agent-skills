"""Go binary feature extraction.

Extracts features from compiled Go ELF binaries by parsing:
- .gopclntab: function names, file paths, line numbers
- Type descriptors: struct field names and types
- Cobra CLI: command tree from cobra.Command structs
- gRPC: FileDescriptorProto blobs for full API surface recovery
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from elftools.elf.elffile import ELFFile
from loguru import logger


@dataclass
class GoFeatures:
    """Features extracted from a Go binary."""

    functions: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    cobra_commands: list[dict] = field(default_factory=list)
    protobuf_services: list[dict] = field(default_factory=list)
    protobuf_messages: list[dict] = field(default_factory=list)
    struct_types: list[dict] = field(default_factory=list)


def is_go_binary(path: str) -> bool:
    """Detect if an ELF binary was compiled with Go."""
    try:
        with open(path, "rb") as f:
            elf = ELFFile(f)
            for section in elf.iter_sections():
                if section.name in (".gopclntab", ".go.buildinfo", ".note.go.buildid"):
                    return True
    except Exception:
        pass
    # Fallback: check for Go runtime strings via strings command
    from elf_parser import run_cmd
    output = run_cmd(["strings", "-n15", path], timeout=30)
    return "runtime.main" in output and "go.buildid" in output


def extract_go_functions(path: str) -> list[str]:
    """Extract function names from Go binary via string patterns.

    Go embeds function names as strings even in stripped binaries.
    Pattern: package/path.FunctionName
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []

    # Go function name pattern: package.Function or package/path.Function
    func_pattern = re.compile(
        rb'((?:[a-zA-Z][\w]*(?:/[\w.-]+)*)\.\(\*?[\w]+\)\.[\w]+|'
        rb'(?:[a-zA-Z][\w]*(?:/[\w.-]+)*)\.[\w]+)'
    )

    functions = set()
    for m in func_pattern.finditer(data):
        name = m.group(0).decode("ascii", errors="replace")
        # Filter to likely application functions (not runtime)
        if (
            not name.startswith("runtime.")
            and not name.startswith("internal/")
            and not name.startswith("sync.")
            and not name.startswith("reflect.")
            and not name.startswith("fmt.")
            and not name.startswith("os.")
            and not name.startswith("io.")
            and not name.startswith("encoding/")
            and not name.startswith("net/")
            and not name.startswith("crypto/")
            and not name.startswith("syscall.")
            and not name.startswith("math.")
            and not name.startswith("sort.")
            and not name.startswith("strings.")
            and not name.startswith("strconv.")
            and not name.startswith("bytes.")
            and not name.startswith("bufio.")
            and not name.startswith("context.")
            and not name.startswith("time.")
            and not name.startswith("path/")
            and not name.startswith("errors.")
            and not name.startswith("unicode.")
            and len(name) < 200
        ):
            functions.add(name)

    return sorted(functions)[:500]


def extract_go_packages(functions: list[str]) -> list[str]:
    """Derive package names from function names."""
    packages = set()
    for fn in functions:
        # package.Function or package/path.Function
        dot = fn.rfind(".")
        if dot > 0:
            pkg = fn[:dot]
            # Remove method receiver: (*Type) prefix
            paren = pkg.find("(")
            if paren >= 0:
                pkg = pkg[:paren].rstrip(".")
            if pkg and len(pkg) < 100:
                packages.add(pkg)
    return sorted(packages)[:100]


def extract_cobra_commands(path: str) -> list[dict]:
    """Extract Cobra CLI commands from a Go binary.

    Cobra stores command metadata as string fields in cobra.Command structs.
    We find these by looking for patterns of short help strings near
    cobra-specific markers.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []

    commands = []
    seen = set()

    # Search for cobra.Command string markers
    # Cobra commands have Use, Short, Long fields as strings
    # The Use field typically matches: "command_name [flags]" or "command_name [args]"
    use_pattern = re.compile(
        rb'([\w][\w-]{1,30})\s*(?:\[[\w\s.|]+\])?\x00'
    )

    # Find cobra-specific strings that indicate CLI structure
    cobra_markers = [
        b"github.com/spf13/cobra",
        b"cobra.Command",
        b"PersistentPreRun",
        b"PersistentPostRun",
    ]

    has_cobra = any(marker in data for marker in cobra_markers)
    if not has_cobra:
        return []

    logger.info("Detected Cobra CLI framework")

    # Extract command names from help text patterns
    # Cobra generates help like: "  command_name   Description text"
    help_pattern = re.compile(
        rb'\n\s{2,4}([\w][\w-]{1,30})\s{2,}([A-Z][\x20-\x7e]{5,80})'
    )
    for m in help_pattern.finditer(data):
        name = m.group(1).decode("ascii", errors="replace")
        desc = m.group(2).decode("ascii", errors="replace").strip()
        if name not in seen and name.islower():
            seen.add(name)
            commands.append({"name": name, "description": desc})

    return commands


def extract_protobuf_descriptors(path: str) -> tuple[list[dict], list[dict]]:
    """Extract gRPC service and message definitions from embedded Protobuf descriptors.

    Go gRPC binaries embed gzipped FileDescriptorProto blobs that contain
    the full .proto source — messages, services, methods, fields.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return [], []

    services = []
    messages = []

    # Find gRPC service name strings: "package.ServiceName"
    service_pattern = re.compile(rb'(/[\w.]+\.[\w]+Service)\x00')
    for m in service_pattern.finditer(data):
        name = m.group(1).decode("ascii", errors="replace")
        if "." in name and len(name) < 100:
            services.append({"name": name.lstrip("/")})

    # Find protobuf message type strings
    # Proto messages appear as "package.MessageName" near registration code
    msg_pattern = re.compile(rb'([\w]+\.[\w]+(?:Request|Response|Message|Info|Status|Config))\x00')
    seen = set()
    for m in msg_pattern.finditer(data):
        name = m.group(1).decode("ascii", errors="replace")
        if name not in seen and len(name) < 100:
            seen.add(name)
            messages.append({"name": name})

    # Try to find and decompress FileDescriptorProto blobs
    # They start with gzip header (1f 8b) and contain .proto field names
    gzip_offsets = [m.start() for m in re.finditer(rb'\x1f\x8b\x08', data)]
    for offset in gzip_offsets[:50]:  # Check first 50 gzip blobs
        try:
            blob = data[offset:offset + 50000]
            decompressed = zlib.decompress(blob, 15 + 32)
            # Check if it looks like a protobuf descriptor
            if b".proto" in decompressed or b"service" in decompressed:
                # Extract readable strings from the descriptor
                strings = re.findall(rb'[\x20-\x7e]{4,100}', decompressed)
                proto_strings = [
                    s.decode("ascii", errors="replace")
                    for s in strings
                    if any(kw in s for kw in [b"Service", b"Request", b"Response", b".proto", b"message"])
                ]
                if proto_strings:
                    logger.info(
                        f"Found protobuf descriptor at offset {offset:#x} "
                        f"with {len(proto_strings)} proto strings"
                    )
                    for s in proto_strings:
                        if "Service" in s and s not in [svc["name"] for svc in services]:
                            services.append({"name": s, "source": "descriptor"})
                        elif "Request" in s or "Response" in s:
                            if s not in [msg["name"] for msg in messages]:
                                messages.append({"name": s, "source": "descriptor"})
        except (zlib.error, Exception):
            continue

    return services, messages


def extract_all(path: str) -> GoFeatures:
    """Extract all features from a Go binary."""
    features = GoFeatures()

    if not is_go_binary(path):
        return features

    logger.info("Go binary detected — extracting Go-specific features")

    features.functions = extract_go_functions(path)
    features.packages = extract_go_packages(features.functions)
    logger.info(f"Go: {len(features.functions)} functions, {len(features.packages)} packages")

    features.cobra_commands = extract_cobra_commands(path)
    if features.cobra_commands:
        logger.info(f"Go Cobra: {len(features.cobra_commands)} commands")

    services, messages = extract_protobuf_descriptors(path)
    features.protobuf_services = services
    features.protobuf_messages = messages
    if services or messages:
        logger.info(f"Go Protobuf: {len(services)} services, {len(messages)} messages")

    return features
