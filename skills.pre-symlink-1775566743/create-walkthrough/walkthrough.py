#!/usr/bin/env python3
"""
Claim Verification Engine for /create-walkthrough.

Parses walkthrough markdown files, extracts factual claims (file paths, function
names, package availability, env vars, port numbers, config values, line counts),
and verifies each against the actual codebase/environment.

Usage:
    python walkthrough.py verify --file walkthrough.md
    python walkthrough.py verify --file walkthrough.md --extract-only
    python walkthrough.py verify --file walkthrough.md --verbose
    python walkthrough.py verify --file walkthrough.md --json
    python walkthrough.py template --file src/pipeline.py --output walkthrough.md
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass  # python-dotenv optional; .env loaded by run.sh

# Ensure skill dir is on path for sibling imports
_skill_dir = str(Path(__file__).resolve().parent)
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from models import Claim, Verdict, VerificationReport  # noqa: E402
from verifiers import verify_claims  # noqa: E402

app = typer.Typer(help="Walkthrough claim verification engine")


# ============================================================================
# Claim Extraction
# ============================================================================

# Match absolute file paths in backticks or after common patterns.
# Requires 2+ path segments to avoid false positives on skill refs like /embedding.
RE_FILE_PATH = re.compile(
    r"`(/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_./-]+)`"
    r"|(?:File:\s*|file\s+)(`?)(/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_./-]+)\2"
)

# Match "filename (N lines)" or "N lines" near a file reference
RE_LINE_COUNT = re.compile(
    r"`([^`]+)`\s*\((\d[\d,]*)\s*lines?\)"
)

# Match function/method names with line references: "func_name() on line N" or "func_name (line N)"
RE_FUNCTION_LINE = re.compile(
    r"`?(\w+)\(\)`?\s*(?:on\s+|at\s+|\()lines?\s*~?(\d+)"
)

# Match function names in backticks followed by contextual clues
RE_FUNCTION_NAME = re.compile(
    r"`(\w+)\(\)`"
)

# Match environment variable defaults: "ENV_VAR defaults to X" or os.environ.get("ENV_VAR", "X")
RE_ENV_DEFAULT = re.compile(
    r"`(\w+)`\s*(?:defaults?\s*to|default(?:s|ing)?\s*(?:is|=))\s*[`\"']?([^`\"'\s,)]+)"
)

# Match port numbers: "port NNNN" or ":NNNN"
RE_PORT = re.compile(
    r"(?:port|PORT)\s+(\d{4,5})|:(\d{4,5})(?:[/\s\)])"
)

# Match "not installed" claims about packages
RE_PACKAGE_MISSING = re.compile(
    r"`(\w[\w.-]+)`\s*(?:not\s+installed|not\s+available|missing|not\s+found)"
)

# Match "installed" or "available" claims
RE_PACKAGE_PRESENT = re.compile(
    r"`(\w[\w.-]+)`\s*(?:is\s+)?(?:installed|available|present|in\s+(?:the\s+)?(?:pyproject|requirements))"
)

# Match numeric claims like "N controls" or "N relationships"
RE_NUMERIC = re.compile(
    r"(\d[\d,]+)\s+(controls?|relationships?|QRAs?|knowledge\s+chunks?|URLs?|edges?)"
)

# Match config value claims: "threshold of X" or "SETTING = X"
RE_CONFIG_VALUE = re.compile(
    r"`?(\w+(?:_\w+)*)`?\s*(?:=|defaults?\s*to|set\s+to|is)\s*[`\"']?([\d.]+)[`\"']?"
)

# Match ArangoDB collection name claims: "`collection_name` collection" or "collection_name` ArangoDB"
RE_COLLECTION = re.compile(
    r"`(\w+)`\s*(?:collection|ArangoDB\s+collection|arango\s+collection)"
    r"|(?:collection|stored?\s+in|from)\s+`(\w+)`",
    re.IGNORECASE,
)

# Match field/attribute claims: "`field_name` field" or "field_name` attribute"
RE_FIELD_NAME = re.compile(
    r"`(\w+)`\s*(?:field|attribute|property|key|column)",
    re.IGNORECASE,
)

# Match TypedDict/class definition claims: "`ClassName` TypedDict" or "`ClassName` class"
RE_CLASS_DEF = re.compile(
    r"`(\w+)`\s*(?:TypedDict|class|dataclass|NamedTuple|BaseModel)",
    re.IGNORECASE,
)

# Match import claims: "from X import Y" or "import X"
RE_IMPORT = re.compile(
    r"`from\s+([\w.]+)\s+import\s+([\w, ]+)`"
    r"|`import\s+([\w.]+)`"
)

# Match relative file paths (no leading /) in backticks — must have extension
RE_RELATIVE_PATH = re.compile(
    r"`((?:\.?[\w.-]+/)+[\w.-]+\.(?:py|ts|js|sh|toml|yaml|yml|json|md))`"
)


def extract_claims(content: str, filepath: str) -> list[Claim]:
    """Extract all verifiable claims from walkthrough markdown."""
    claims = []
    lines = content.split("\n")

    for i, line in enumerate(lines, 1):
        # Skip code blocks (``` fenced)
        # Simple heuristic: skip lines inside code blocks
        # (A full parser would track block state)

        # File paths
        for m in RE_FILE_PATH.finditer(line):
            path = m.group(1) or m.group(3)
            if path and len(path) > 3 and not path.startswith("/tmp"):
                claims.append(Claim(
                    claim_type="file_path",
                    raw_text=line.strip(),
                    value=path,
                    line_number=i,
                ))

        # Line counts
        for m in RE_LINE_COUNT.finditer(line):
            fname = m.group(1)
            count = m.group(2).replace(",", "")
            claims.append(Claim(
                claim_type="line_count",
                raw_text=line.strip(),
                value=f"{fname}:{count}",
                line_number=i,
            ))

        # Function + line references
        for m in RE_FUNCTION_LINE.finditer(line):
            func_name = m.group(1)
            line_num = m.group(2)
            claims.append(Claim(
                claim_type="function_line",
                raw_text=line.strip(),
                value=f"{func_name}:{line_num}",
                line_number=i,
            ))

        # Environment variable defaults
        for m in RE_ENV_DEFAULT.finditer(line):
            env_var = m.group(1)
            default = m.group(2)
            claims.append(Claim(
                claim_type="env_default",
                raw_text=line.strip(),
                value=f"{env_var}={default}",
                line_number=i,
            ))

        # Port numbers
        for m in RE_PORT.finditer(line):
            port = m.group(1) or m.group(2)
            claims.append(Claim(
                claim_type="port",
                raw_text=line.strip(),
                value=port,
                line_number=i,
            ))

        # Package missing claims
        for m in RE_PACKAGE_MISSING.finditer(line):
            pkg = m.group(1)
            claims.append(Claim(
                claim_type="package_missing",
                raw_text=line.strip(),
                value=pkg,
                line_number=i,
            ))

        # Package present claims
        for m in RE_PACKAGE_PRESENT.finditer(line):
            pkg = m.group(1)
            claims.append(Claim(
                claim_type="package_present",
                raw_text=line.strip(),
                value=pkg,
                line_number=i,
            ))

        # ArangoDB collection claims
        for m in RE_COLLECTION.finditer(line):
            name = m.group(1) or m.group(2)
            if name and len(name) > 2 and name not in ("the", "this", "each", "all"):
                claims.append(Claim(
                    claim_type="collection",
                    raw_text=line.strip(),
                    value=name,
                    line_number=i,
                ))

        # Field/attribute claims
        for m in RE_FIELD_NAME.finditer(line):
            field_name = m.group(1)
            if field_name and len(field_name) > 2:
                claims.append(Claim(
                    claim_type="field_name",
                    raw_text=line.strip(),
                    value=field_name,
                    line_number=i,
                ))

        # TypedDict/class definition claims
        for m in RE_CLASS_DEF.finditer(line):
            class_name = m.group(1)
            claims.append(Claim(
                claim_type="class_def",
                raw_text=line.strip(),
                value=class_name,
                line_number=i,
            ))

        # Import statement claims
        for m in RE_IMPORT.finditer(line):
            if m.group(1):  # from X import Y
                module = m.group(1)
                names = m.group(2)
                claims.append(Claim(
                    claim_type="import_from",
                    raw_text=line.strip(),
                    value=f"{module}:{names.strip()}",
                    line_number=i,
                ))
            elif m.group(3):  # import X
                claims.append(Claim(
                    claim_type="import_module",
                    raw_text=line.strip(),
                    value=m.group(3),
                    line_number=i,
                ))

        # Relative file paths (with extensions)
        for m in RE_RELATIVE_PATH.finditer(line):
            rel_path = m.group(1)
            # Skip if already captured as absolute path
            if not rel_path.startswith("/") and "/" in rel_path:
                claims.append(Claim(
                    claim_type="relative_path",
                    raw_text=line.strip(),
                    value=rel_path,
                    line_number=i,
                ))

    # Deduplicate by (type, value, line)
    seen = set()
    unique = []
    for c in claims:
        key = (c.claim_type, c.value, c.line_number)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


# ============================================================================
# Claim Verification (delegated to verifiers.py)
# ============================================================================
# verify_claims imported at top of file from verifiers.py


# ============================================================================
# Output Formatting
# ============================================================================

VERDICT_COLORS = {
    Verdict.VERIFIED: "\033[32m",    # green
    Verdict.MISMATCH: "\033[31m",    # red
    Verdict.UNVERIFIED: "\033[33m",  # yellow
    Verdict.SKIPPED: "\033[90m",     # gray
}
RESET = "\033[0m"


def format_claim(claim: Claim, verbose: bool = False) -> str:
    """Format a single claim result for terminal output."""
    color = VERDICT_COLORS.get(claim.verdict, "")
    tag = f"{color}{claim.verdict.value:12s}{RESET}" if claim.verdict else "PENDING     "
    line = f"  {tag}: {claim.detail}"
    if verbose:
        line += f"\n               raw: {claim.raw_text[:100]}"
    return line


def format_report(report: VerificationReport, verbose: bool = False) -> str:
    """Format the full verification report."""
    lines = [
        f"Walkthrough Claim Verification: {report.file}",
        f"{'=' * 60}",
        f"  Total claims: {len(report.claims)}",
        f"  Verified:     {report.verified}",
        f"  Mismatched:   {report.mismatched}",
        f"  Unverified:   {report.unverified}",
        f"  Skipped:      {report.skipped}",
        "",
    ]

    # Group by verdict for readability
    for verdict in [Verdict.MISMATCH, Verdict.UNVERIFIED, Verdict.VERIFIED, Verdict.SKIPPED]:
        group = [c for c in report.claims if c.verdict == verdict]
        if group:
            lines.append(f"--- {verdict.value} ({len(group)}) ---")
            for claim in group:
                lines.append(format_claim(claim, verbose))
            lines.append("")

    # Summary
    if report.mismatched > 0:
        lines.append(
            f"\033[31mACTION REQUIRED: {report.mismatched} claim(s) do not match reality.\033[0m"
        )
        lines.append("Fix these before presenting the walkthrough to the user.")
    elif report.unverified > 0:
        lines.append(
            f"\033[33mWARNING: {report.unverified} claim(s) could not be verified.\033[0m"
        )
        lines.append("Flag these for manual user review.")
    else:
        lines.append("\033[32mAll verifiable claims confirmed.\033[0m")

    return "\n".join(lines)


# ============================================================================
# CLI Commands
# ============================================================================


@app.command()
def verify(
    file: str = typer.Option(..., "-f", "--file", help="Walkthrough markdown file"),
    extract_only: bool = typer.Option(False, "--extract-only", help="Only extract claims, don't verify"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show raw text for each claim"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Verify all factual claims in a walkthrough document."""
    path = Path(file)
    if not path.exists():
        logger.error(f"{file} not found")
        raise typer.Exit(1)

    content = path.read_text()
    claims = extract_claims(content, file)

    if extract_only:
        print(f"Extracted {len(claims)} claims from {file}:\n")
        for c in claims:
            print(f"  [{c.claim_type:16s}] line {c.line_number:4d}: {c.value}")
        raise typer.Exit(0)

    # Change to the project directory if the file is under a project
    project_dir = _find_project_root(path)
    if project_dir:
        os.chdir(project_dir)

    verified = verify_claims(claims)
    report = VerificationReport(file=file, claims=verified)

    if output_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report, verbose))

    # Exit with non-zero if there are mismatches
    if report.mismatched > 0:
        raise typer.Exit(2)


@app.command()
def template(
    file: str = typer.Option(..., "-f", "--file", help="Main implementation file"),
    output: str = typer.Option("walkthrough.md", "-o", "--output", help="Output file"),
    include_git: bool = typer.Option(False, "--include-git", help="Include git history"),
):
    """Generate a blank walkthrough template for a file."""
    path = Path(file)
    if not path.exists():
        logger.error(f"{file} not found")
        raise typer.Exit(1)

    line_count = sum(1 for _ in open(path))
    basename = path.name
    today = __import__("datetime").date.today().isoformat()

    git_section = ""
    if include_git:
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-20", "--", str(path)],
                capture_output=True, text=True, timeout=10,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.stdout.strip():
                git_section = (
                    f"\n### Recent Git History\n\n```\n"
                    f"{result.stdout.strip()}\n```\n"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Load template from references/ (progressive disclosure)
    template_path = Path(__file__).parent / "references" / "walkthrough_template.md"
    if not template_path.exists():
        logger.error(f"Template not found: {template_path}")
        raise typer.Exit(1)

    template_content = template_path.read_text()
    template_content = (
        template_content
        .replace("{{DATE}}", today)
        .replace("{{FILE}}", file)
        .replace("{{LINE_COUNT}}", f"{line_count:,}")
        .replace("{{GIT_SECTION}}", git_section)
    )

    Path(output).write_text(template_content)
    print(f"Template written to {output} ({line_count:,} lines in {basename})")


def _find_project_root(path: Path) -> Optional[Path]:
    """Walk up from path looking for project markers."""
    current = path.resolve().parent
    markers = ["pyproject.toml", "package.json", "Cargo.toml", ".git"]
    for _ in range(10):
        if any((current / m).exists() for m in markers):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


@app.command()
def learn(
    file: str = typer.Option(..., "-f", "--file", help="Walkthrough markdown file"),
    system_name: str = typer.Option("", "-s", "--system", help="System name (auto-detected from filename)"),
    bottom_line: str = typer.Option("", "--bottom-line", help="Bottom-line assessment"),
):
    """Learn walkthrough findings to memory after verification."""
    path = Path(file)
    if not path.exists():
        logger.error(f"{file} not found")
        raise typer.Exit(1)

    # Auto-detect system name from filename if not provided
    if not system_name:
        system_name = path.stem.replace("walkthrough_", "").replace("_walkthrough", "")

    # Run verification first to get stats
    content = path.read_text()
    claims = extract_claims(content, file)
    project_dir = _find_project_root(path)
    if project_dir:
        os.chdir(project_dir)
    verified = verify_claims(claims)
    report = VerificationReport(file=file, claims=verified)

    # Extract risks from walkthrough content (lines starting with risk markers)
    risks = []
    for line in content.split("\n"):
        stripped = line.strip()
        if any(stripped.lower().startswith(marker) for marker in
               ["- risk:", "- **risk", "risk:", "what could go wrong"]):
            risks.append(stripped.lstrip("- "))

    try:
        from memory_integration import learn_walkthrough
        ids = learn_walkthrough(
            walkthrough_path=file,
            system_name=system_name,
            verification_summary={
                "total": len(report.claims),
                "verified": report.verified,
                "mismatched": report.mismatched,
                "unverified": report.unverified,
            },
            risks=risks,
            bottom_line=bottom_line,
        )
        print(f"Learned {len(ids)} entries to memory for system '{system_name}'")
    except ImportError:
        logger.warning("memory_integration not available")
        raise typer.Exit(1)


@app.command()
def recall(
    system_name: str = typer.Argument(..., help="System name to recall prior walkthroughs for"),
    k: int = typer.Option(5, "-k", help="Number of results"),
):
    """Recall prior walkthrough findings from memory."""
    try:
        from memory_integration import recall_prior_walkthroughs
        context = recall_prior_walkthroughs(system_name, k=k)
        if context:
            print(context)
        else:
            print(f"No prior walkthroughs found for '{system_name}'")
    except ImportError:
        logger.warning("memory_integration not available")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
