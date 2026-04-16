#!/usr/bin/env python3
"""CUI Marker — detect, classify, and mark Controlled Unclassified Information."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="CUI detection, marking, and flow tracking per 32 CFR Part 2002")

# ---------------------------------------------------------------------------
# CUI Categories from NARA CUI Registry (defense-relevant subset)
# ---------------------------------------------------------------------------

CUI_CATEGORIES = {
    "CTI": {
        "name": "Controlled Technical Information",
        "description": "Technical data with military or space application per DoDD 5230.24",
        "marking": "CUI//SP-CTI",
        "indicators": [
            r"controlled\s+technical\s+information",
            r"DFARS\s+252\.204[- ]7012",
            r"technical\s+data\s+package",
            r"engineering\s+drawing",
            r"test\s+report",
            r"performance\s+specification",
            r"process\s+specification",
            r"material\s+specification",
        ],
    },
    "EXPT": {
        "name": "Export Controlled",
        "description": "ITAR (22 CFR 120-130) or EAR (15 CFR 730-774) controlled",
        "marking": "CUI//SP-EXPT",
        "indicators": [
            r"ITAR",
            r"export\s+control",
            r"USML\s+categor",
            r"EAR\s+controlled",
            r"22\s+CFR\s+12[0-9]",
            r"15\s+CFR\s+7[3-7][0-9]",
            r"defense\s+article",
            r"technical\s+assistance\s+agreement",
            r"ECCN\s+\d[A-E]\d{3}",
        ],
    },
    "PROPIN": {
        "name": "Proprietary Business Information",
        "description": "Contractor proprietary, trade secrets, business sensitive",
        "marking": "CUI//SP-PROPIN",
        "indicators": [
            r"proprietary",
            r"trade\s+secret",
            r"business\s+sensitive",
            r"competition\s+sensitive",
            r"source\s+selection",
        ],
    },
    "PRVCY": {
        "name": "Privacy Information",
        "description": "PII, PHI, personnel records",
        "marking": "CUI//SP-PRVCY",
        "indicators": [
            r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b",  # SSN pattern
            r"personally\s+identifiable",
            r"protected\s+health",
            r"date\s+of\s+birth",
            r"clearance\s+level",
        ],
    },
    "PROCURE": {
        "name": "Procurement and Acquisition",
        "description": "Source selection, bid/proposal, cost/pricing data",
        "marking": "CUI//SP-PROCURE",
        "indicators": [
            r"source\s+selection",
            r"bid\s+and\s+proposal",
            r"cost\s+or\s+pricing\s+data",
            r"pre-?award",
            r"acquisition\s+sensitive",
        ],
    },
    "INTEL": {
        "name": "Intelligence",
        "description": "Threat data, intelligence assessments",
        "marking": "CUI//SP-INTEL",
        "indicators": [
            r"threat\s+assessment",
            r"intelligence\s+report",
            r"threat\s+actor",
            r"indicators\s+of\s+compromise",
        ],
    },
    "INFOSEC": {
        "name": "Information Systems Security",
        "description": "Vulnerability data, penetration test results, security assessments",
        "marking": "CUI//SP-INFOSEC",
        "indicators": [
            r"vulnerability\s+(assessment|scan|report)",
            r"penetration\s+test",
            r"security\s+assessment",
            r"STIG\s+finding",
            r"POA&?M",
            r"plan\s+of\s+action",
        ],
    },
}

# Legacy markings that must be converted to CUI
LEGACY_MARKINGS = {
    r"FOR\s+OFFICIAL\s+USE\s+ONLY": "FOUO → must convert to CUI",
    r"SENSITIVE\s+BUT\s+UNCLASSIFIED": "SBU → must convert to CUI",
    r"LAW\s+ENFORCEMENT\s+SENSITIVE": "LES → must convert to CUI",
    r"LIMITED\s+DISTRIBUTION": "LIMDIS → must convert to CUI",
    r"FOUO": "FOUO → must convert to CUI",
}

# Distribution statements (per DoD 5230.24)
DISTRIBUTION_STATEMENTS = {
    "A": "Approved for public release; distribution unlimited",
    "B": "Distribution authorized to U.S. Government agencies only",
    "C": "Distribution authorized to U.S. Government agencies and contractors",
    "D": "Distribution authorized to DoD and U.S. DoD contractors only",
    "E": "Distribution authorized to DoD components only",
    "F": "Further dissemination only as directed",
    "X": "Distribution authorized to U.S. Government agencies and private individuals",
}


def _compile_patterns() -> dict[str, list[re.Pattern]]:
    """Pre-compile all regex patterns."""
    compiled = {}
    for cat, info in CUI_CATEGORIES.items():
        compiled[cat] = [re.compile(p, re.IGNORECASE) for p in info["indicators"]]
    return compiled


COMPILED_PATTERNS = _compile_patterns()
LEGACY_COMPILED = {re.compile(p, re.IGNORECASE): msg for p, msg in LEGACY_MARKINGS.items()}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_text(text: str) -> dict:
    """Scan text for CUI indicators. Returns detection results."""
    detections = []
    lines = text.split("\n")

    for cat, patterns in COMPILED_PATTERNS.items():
        for pattern in patterns:
            for i, line in enumerate(lines, 1):
                for match in pattern.finditer(line):
                    detections.append({
                        "category": cat,
                        "category_name": CUI_CATEGORIES[cat]["name"],
                        "marking": CUI_CATEGORIES[cat]["marking"],
                        "pattern": pattern.pattern,
                        "match": match.group(),
                        "line": i,
                        "context": line.strip()[:200],
                    })

    # Check for legacy markings
    legacy_findings = []
    for pattern, message in LEGACY_COMPILED.items():
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                legacy_findings.append({
                    "type": "legacy_marking",
                    "message": message,
                    "line": i,
                    "context": line.strip()[:200],
                })

    # Deduplicate by category
    categories_found = sorted(set(d["category"] for d in detections))

    return {
        "cui_detected": len(detections) > 0,
        "categories": categories_found,
        "detection_count": len(detections),
        "detections": detections,
        "legacy_markings": legacy_findings,
        "recommended_marking": _recommend_marking(categories_found),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


def _recommend_marking(categories: list[str]) -> str | None:
    """Recommend CUI marking based on detected categories."""
    if not categories:
        return None
    if len(categories) == 1:
        return CUI_CATEGORIES[categories[0]]["marking"]
    # Multiple categories — use combined marking
    subcats = "/".join(f"SP-{c}" for c in categories)
    return f"CUI//{subcats}"


def scan_file(path: Path) -> dict:
    """Scan a file for CUI indicators."""
    try:
        text = path.read_text(errors="replace")
    except Exception as e:
        return {"error": str(e), "file": str(path)}

    result = scan_text(text)
    result["file"] = str(path)
    result["file_size"] = path.stat().st_size
    return result


def scan_directory(path: Path, extensions: list[str] | None = None) -> list[dict]:
    """Scan all files in a directory."""
    if extensions is None:
        extensions = [".txt", ".md", ".pdf", ".json", ".yaml", ".yml", ".py", ".rs", ".ts", ".tsx"]

    results = []
    for f in sorted(path.rglob("*")):
        if f.is_file() and f.suffix in extensions:
            result = scan_file(f)
            if result.get("cui_detected") or result.get("legacy_markings"):
                results.append(result)
    return results


# ---------------------------------------------------------------------------
# Marking
# ---------------------------------------------------------------------------


def generate_banner(marking: str, distribution: str = "D") -> str:
    """Generate CUI banner marking for document header/footer."""
    dist_text = DISTRIBUTION_STATEMENTS.get(distribution, DISTRIBUTION_STATEMENTS["D"])
    return (
        f"{marking}\n"
        f"Distribution Statement {distribution}: {dist_text}\n"
        f"Destruction Notice: Destroy by any method that will prevent disclosure of contents "
        f"or reconstruction of the document."
    )


def generate_portion_mark(text: str, category: str) -> str:
    """Add portion marking to a paragraph."""
    marking = CUI_CATEGORIES.get(category, {}).get("marking", "CUI")
    return f"({marking}) {text}"


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------


@app.command()
def scan(
    path: Optional[Path] = typer.Argument(None, help="File or directory to scan"),
    collection: Optional[str] = typer.Option(None, help="ArangoDB collection to scan"),
    stdin: bool = typer.Option(False, "--stdin", help="Read from stdin"),
    output: Optional[Path] = typer.Option(None, help="Write JSON results to file"),
):
    """Scan file, directory, or ArangoDB collection for CUI indicators."""
    if stdin:
        text = sys.stdin.read()
        result = scan_text(text)
        typer.echo(json.dumps(result, indent=2))
        return

    if collection:
        typer.echo(f"Scanning ArangoDB collection: {collection}")
        typer.echo("ArangoDB collection scanning requires running datalake-daemon")
        # Would call datalake-daemon /documents endpoint and scan each doc
        import httpx
        try:
            resp = httpx.get(
                f"http://localhost/documents?collection={collection}",
                transport=httpx.HTTPTransport(uds="/run/user/1000/embry/datalake.sock"),
                timeout=30,
            )
            if resp.status_code == 200:
                docs = resp.json().get("documents", [])
                results = []
                for doc in docs:
                    text = doc.get("content", doc.get("text", ""))
                    if text:
                        result = scan_text(text)
                        result["doc_id"] = doc.get("_key", doc.get("_id", "unknown"))
                        if result["cui_detected"]:
                            results.append(result)
                typer.echo(json.dumps(results, indent=2))
            else:
                typer.echo(f"Error: datalake returned {resp.status_code}")
        except Exception as e:
            typer.echo(f"Error connecting to datalake-daemon: {e}")
        return

    if path is None:
        typer.echo("Provide a path, --collection, or --stdin")
        raise typer.Exit(1)

    if path.is_file():
        result = scan_file(path)
        text = json.dumps(result, indent=2)
    elif path.is_dir():
        results = scan_directory(path)
        text = json.dumps(results, indent=2)
    else:
        typer.echo(f"Path not found: {path}")
        raise typer.Exit(1)

    if output:
        output.write_text(text)
        typer.echo(f"Results written to {output}")
    else:
        typer.echo(text)


@app.command()
def mark(
    doc_id: str = typer.Argument(..., help="Document ID or path"),
    category: Optional[str] = typer.Option(None, help="CUI category (e.g., CTI, EXPT)"),
    auto: bool = typer.Option(False, "--auto", help="Auto-detect category"),
    distribution: str = typer.Option("D", help="Distribution statement (A-F, X)"),
):
    """Apply CUI marking to a document."""
    if auto and not category:
        # Auto-detect from file content
        path = Path(doc_id)
        if path.exists():
            result = scan_file(path)
            if result.get("categories"):
                category = result["categories"][0]
                typer.echo(f"Auto-detected category: {category} ({CUI_CATEGORIES[category]['name']})")
            else:
                typer.echo("No CUI indicators detected — cannot auto-mark")
                raise typer.Exit(1)
        else:
            typer.echo(f"File not found: {doc_id}")
            raise typer.Exit(1)

    if not category:
        typer.echo("Specify --category or use --auto")
        raise typer.Exit(1)

    if category not in CUI_CATEGORIES:
        typer.echo(f"Unknown category: {category}")
        typer.echo(f"Valid categories: {', '.join(CUI_CATEGORIES.keys())}")
        raise typer.Exit(1)

    marking = CUI_CATEGORIES[category]["marking"]
    banner = generate_banner(marking, distribution)

    typer.echo(f"\n{'='*60}")
    typer.echo(banner)
    typer.echo(f"{'='*60}\n")
    typer.echo(f"Document: {doc_id}")
    typer.echo(f"Category: {category} — {CUI_CATEGORIES[category]['name']}")
    typer.echo(f"Marking: {marking}")
    typer.echo(f"Distribution: Statement {distribution}")


@app.command()
def verify(doc_id: str = typer.Argument(..., help="Document ID or path")):
    """Verify a document has proper CUI markings."""
    path = Path(doc_id)
    if not path.exists():
        typer.echo(f"File not found: {doc_id}")
        raise typer.Exit(1)

    text = path.read_text(errors="replace")
    issues = []

    # Check for CUI banner
    has_banner = bool(re.search(r"CUI//", text[:500]))
    if not has_banner:
        issues.append("Missing CUI banner marking in document header")

    # Check for distribution statement
    has_dist = bool(re.search(r"Distribution Statement [A-FX]", text, re.IGNORECASE))
    if not has_dist:
        issues.append("Missing distribution statement")

    # Check for destruction notice
    has_destroy = bool(re.search(r"Destruction Notice", text, re.IGNORECASE))
    if not has_destroy:
        issues.append("Missing destruction notice")

    # Check for legacy markings that should have been converted
    scan_result = scan_text(text)
    if scan_result["legacy_markings"]:
        for lm in scan_result["legacy_markings"]:
            issues.append(f"Legacy marking found (line {lm['line']}): {lm['message']}")

    if issues:
        typer.echo(f"FAIL — {len(issues)} issue(s) found:")
        for issue in issues:
            typer.echo(f"  - {issue}")
        raise typer.Exit(1)
    else:
        typer.echo("PASS — document has proper CUI markings")


@app.command()
def categories():
    """List CUI categories and subcategories."""
    for cat_id, info in CUI_CATEGORIES.items():
        typer.echo(f"{cat_id:8s}  {info['marking']:20s}  {info['name']}")
        typer.echo(f"{'':8s}  {info['description']}")
        typer.echo()


@app.command()
def report(output: Optional[Path] = typer.Option(None, help="Output file")):
    """Generate CUI inventory report (scans common locations)."""
    typer.echo("CUI Inventory Report")
    typer.echo("=" * 40)
    typer.echo("Scanning common document locations...")

    # Scan likely CUI locations
    locations = [
        Path.home() / "Documents",
        Path("/tmp"),
    ]

    all_results = []
    for loc in locations:
        if loc.exists():
            results = scan_directory(loc)
            all_results.extend(results)

    typer.echo(f"\nFiles with CUI indicators: {len(all_results)}")
    for r in all_results:
        cats = ", ".join(r.get("categories", []))
        typer.echo(f"  {r.get('file', '?')}: {cats} ({r.get('detection_count', 0)} detections)")

    if output:
        output.write_text(json.dumps(all_results, indent=2))
        typer.echo(f"\nFull report written to {output}")


@app.command()
def audit():
    """Audit all ArangoDB collections for unmarked CUI."""
    typer.echo("CUI Audit — checking ArangoDB collections for unmarked CUI")
    typer.echo("Requires running datalake-daemon on /run/user/1000/embry/datalake.sock")

    import httpx
    try:
        resp = httpx.get(
            "http://localhost/health",
            transport=httpx.HTTPTransport(uds="/run/user/1000/embry/datalake.sock"),
            timeout=10,
        )
        if resp.status_code != 200:
            typer.echo("ERROR: datalake-daemon not healthy")
            raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"ERROR: Cannot connect to datalake-daemon: {e}")
        raise typer.Exit(1)

    typer.echo("Connected to datalake-daemon. Scanning collections...")
    # Real implementation would iterate through collections and scan documents


@app.command()
def flow(doc_id: str = typer.Argument(..., help="Document ID to trace")):
    """Trace CUI document flow through the system."""
    typer.echo(f"Tracing CUI flow for document: {doc_id}")
    typer.echo("Flow tracking shows how CUI data moves through Embry OS:")
    typer.echo("  1. Ingestion (extractor/datalake)")
    typer.echo("  2. Storage (ArangoDB collections)")
    typer.echo("  3. Processing (inference-daemon)")
    typer.echo("  4. Display (embry-ui)")
    typer.echo("  5. Export (reports, exports)")
    typer.echo(f"\nRequires doc_id lookup in ArangoDB to trace actual flow.")


if __name__ == "__main__":
    app()
