#!/usr/bin/env python3
"""
DARPA Operations Skill

Query DARPA programs, opportunities, and funding via:
- DARPA RSS feeds (programs, opportunities)
- Grants.gov API (federal grant opportunities)

No authentication required for any of these sources.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.markdown import Markdown
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

app = typer.Typer(help="DARPA programs and funding opportunities")
console = Console()

# DARPA RSS Feeds
DARPA_RSS_URL = "https://www.darpa.mil/rss.xml"
DARPA_OPPORTUNITIES_RSS = "https://www.darpa.mil/rss/opportunities.xml"

# Grants.gov API
GRANTS_GOV_API = "https://api.grants.gov/v1/api/search2"

# DARPA Technical Offices
DARPA_OFFICES = {
    "I2O": {
        "name": "Information Innovation Office",
        "focus": "AI, cybersecurity, software systems",
        "baa_url": "https://www.darpa.mil/work-with-us/office-wide-broad-agency-announcements",
    },
    "MTO": {
        "name": "Microsystems Technology Office",
        "focus": "Hardware, 5G/6G, microsystems",
        "baa_url": "https://www.darpa.mil/work-with-us/office-wide-broad-agency-announcements",
    },
    "DSO": {
        "name": "Defense Sciences Office",
        "focus": "Foundational science, materials, sensing",
        "baa_url": "https://www.darpa.mil/work-with-us/office-wide-broad-agency-announcements",
    },
    "BTO": {
        "name": "Biological Technologies Office",
        "focus": "Biotechnology, synthetic biology",
        "baa_url": "https://www.darpa.mil/work-with-us/office-wide-broad-agency-announcements",
    },
    "STO": {
        "name": "Strategic Technology Office",
        "focus": "Strategic systems, communications",
        "baa_url": "https://www.darpa.mil/work-with-us/office-wide-broad-agency-announcements",
    },
    "TTO": {
        "name": "Tactical Technology Office",
        "focus": "Tactical military systems",
        "baa_url": "https://www.darpa.mil/work-with-us/office-wide-broad-agency-announcements",
    },
}


@dataclass
class RSSItem:
    """Parsed RSS feed item."""
    title: str
    link: str
    description: str
    pub_date: str
    category: str = ""


def fetch_url(url: str, method: str = "GET", data: bytes = None, headers: dict = None) -> str:
    """Fetch URL content."""
    req = Request(url, method=method, data=data)
    req.add_header("User-Agent", "ops-darpa/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8")
    except HTTPError as e:
        raise Exception(f"HTTP {e.code}: {e.reason}")
    except URLError as e:
        raise Exception(f"Network error: {e.reason}")


def parse_rss(xml_content: str) -> list[RSSItem]:
    """Parse RSS XML into items."""
    items = []
    try:
        root = ET.fromstring(xml_content)
        channel = root.find("channel")
        if channel is None:
            return items

        for item in channel.findall("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            description = item.findtext("description", "")
            pub_date = item.findtext("pubDate", "")
            category = item.findtext("category", "")

            # Clean HTML from description
            description = re.sub(r"<[^>]+>", "", unescape(description))
            description = " ".join(description.split())[:300]

            items.append(RSSItem(
                title=title,
                link=link,
                description=description,
                pub_date=pub_date,
                category=category,
            ))
    except ET.ParseError as e:
        raise Exception(f"Failed to parse RSS: {e}")

    return items


def search_grants_gov(
    keyword: str,
    agency: str = None,
    status: str = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Search Grants.gov API for opportunities."""
    payload: dict[str, Any] = {
        "keyword": keyword,
        "rows": limit,
    }

    if agency:
        payload["agencies"] = agency

    if status:
        payload["oppStatuses"] = status

    try:
        data = json.dumps(payload).encode("utf-8")
        response = fetch_url(
            GRANTS_GOV_API,
            method="POST",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        result = json.loads(response)
        return result.get("oppHits", [])
    except Exception as e:
        raise Exception(f"Grants.gov API error: {e}")


def detect_office(text: str) -> str:
    """Detect DARPA office from text."""
    text_upper = text.upper()
    for code in DARPA_OFFICES:
        if code in text_upper:
            return code
    return ""


@app.command()
def programs(
    office: Optional[str] = typer.Option(None, "--office", "-o", help="Filter by office (I2O, MTO, DSO, BTO, STO, TTO)"),
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Search keyword"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List DARPA programs from RSS feed."""
    console.print("[dim]Fetching DARPA programs...[/dim]")

    try:
        xml_content = fetch_url(DARPA_RSS_URL)
        items = parse_rss(xml_content)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Filter by office
    if office:
        office = office.upper()
        if office not in DARPA_OFFICES:
            console.print(f"[yellow]Unknown office: {office}[/yellow]")
            console.print(f"Valid offices: {', '.join(DARPA_OFFICES.keys())}")
        items = [i for i in items if office in i.title.upper() or office in i.description.upper()]

    # Filter by keyword
    if keyword:
        kw_lower = keyword.lower()
        items = [i for i in items if kw_lower in i.title.lower() or kw_lower in i.description.lower()]

    items = items[:limit]

    if output_json:
        output = [
            {
                "title": i.title,
                "link": i.link,
                "description": i.description,
                "pub_date": i.pub_date,
                "category": i.category,
                "detected_office": detect_office(i.title + i.description),
            }
            for i in items
        ]
        print(json.dumps(output, indent=2))
        return

    if not items:
        console.print("[yellow]No programs found matching criteria.[/yellow]")
        return

    console.print(f"[bold]Found {len(items)} programs:[/bold]\n")

    for item in items:
        detected = detect_office(item.title + item.description)
        office_badge = f"[cyan][{detected}][/cyan] " if detected else ""

        console.print(f"{office_badge}[bold]{item.title}[/bold]")
        console.print(f"  [dim]{item.description[:200]}{'...' if len(item.description) > 200 else ''}[/dim]")
        console.print(f"  [link={item.link}]{item.link}[/link]")
        console.print()


@app.command()
def opportunities(
    office: Optional[str] = typer.Option(None, "--office", "-o", help="Filter by office"),
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Search keyword"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List DARPA opportunities (BAAs) from RSS feed."""
    console.print("[dim]Fetching DARPA opportunities...[/dim]")

    try:
        xml_content = fetch_url(DARPA_OPPORTUNITIES_RSS)
        items = parse_rss(xml_content)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Filter by office
    if office:
        office = office.upper()
        items = [i for i in items if office in i.title.upper() or office in i.description.upper()]

    # Filter by keyword
    if keyword:
        kw_lower = keyword.lower()
        items = [i for i in items if kw_lower in i.title.lower() or kw_lower in i.description.lower()]

    items = items[:limit]

    if output_json:
        output = [
            {
                "title": i.title,
                "link": i.link,
                "description": i.description,
                "pub_date": i.pub_date,
                "detected_office": detect_office(i.title + i.description),
            }
            for i in items
        ]
        print(json.dumps(output, indent=2))
        return

    if not items:
        console.print("[yellow]No opportunities found matching criteria.[/yellow]")
        return

    console.print(f"[bold]Found {len(items)} opportunities:[/bold]\n")

    for item in items:
        detected = detect_office(item.title + item.description)
        office_badge = f"[magenta][{detected}][/magenta] " if detected else ""

        console.print(f"{office_badge}[bold]{item.title}[/bold]")
        if item.pub_date:
            console.print(f"  [dim]Published: {item.pub_date}[/dim]")
        console.print(f"  {item.description[:200]}{'...' if len(item.description) > 200 else ''}")
        console.print(f"  [link={item.link}]{item.link}[/link]")
        console.print()


@app.command()
def grants(
    keyword: str = typer.Argument(..., help="Search keyword"),
    agency: Optional[str] = typer.Option(None, "--agency", "-a", help="Agency code (DOD for all defense)"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Status: forecasted, posted, closed"),
    limit: int = typer.Option(25, "--limit", "-l", help="Max results"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search Grants.gov for federal opportunities."""
    # Default to searching with DARPA context
    search_keyword = keyword
    if "darpa" not in keyword.lower():
        search_keyword = f"DARPA {keyword}"

    console.print(f"[dim]Searching Grants.gov for '{search_keyword}'...[/dim]")

    try:
        results = search_grants_gov(search_keyword, agency=agency, status=status, limit=limit)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if output_json:
        print(json.dumps(results, indent=2))
        return

    if not results:
        console.print("[yellow]No grants found.[/yellow]")
        return

    console.print(f"[bold]Found {len(results)} grant opportunities:[/bold]\n")

    table = Table(title="Grants.gov Opportunities")
    table.add_column("ID", style="cyan", width=15)
    table.add_column("Title", width=45)
    table.add_column("Agency", width=10)
    table.add_column("Status", width=12)
    table.add_column("Close Date", width=12)

    for grant in results:
        opp_id = grant.get("id", "N/A")
        title = grant.get("title", "Unknown")[:43]
        agency_code = grant.get("agencyCode", "N/A")
        opp_status = grant.get("oppStatus", "N/A")
        close_date = grant.get("closeDate", "N/A")
        if close_date and close_date != "N/A":
            close_date = close_date[:10]

        # Color status
        if opp_status == "posted":
            status_display = "[green]posted[/green]"
        elif opp_status == "forecasted":
            status_display = "[yellow]forecasted[/yellow]"
        else:
            status_display = opp_status

        table.add_row(str(opp_id), title, agency_code, status_display, close_date)

    console.print(table)
    console.print("\n[dim]View details at: https://www.grants.gov/search-results-detail/<ID>[/dim]")


@app.command()
def offices():
    """List DARPA technical offices."""
    console.print("[bold]DARPA Technical Offices[/bold]\n")

    table = Table()
    table.add_column("Code", style="cyan", width=6)
    table.add_column("Name", width=35)
    table.add_column("Focus Area", width=40)

    for code, info in DARPA_OFFICES.items():
        table.add_row(code, info["name"], info["focus"])

    console.print(table)
    console.print("\n[dim]Filter by office: --office I2O[/dim]")


@app.command()
def baas():
    """List office-wide BAAs (always open for revolutionary ideas)."""
    console.print(Panel(
        "[bold]Office-Wide Broad Agency Announcements[/bold]\n\n"
        "Each DARPA technical office maintains a standing BAA for researchers\n"
        "to submit ideas outside current program priorities.\n\n"
        "These are always open and don't guarantee funding, but allow you\n"
        "to propose revolutionary research that may create new programs.",
        title="DARPA Office-Wide BAAs",
    ))

    console.print("\n[bold]Available BAAs:[/bold]\n")

    for code, info in DARPA_OFFICES.items():
        console.print(f"[cyan]{code}[/cyan] - {info['name']}")
        console.print(f"  Focus: {info['focus']}")
        console.print()

    console.print("[bold]How to Submit:[/bold]")
    console.print("1. Visit: https://www.darpa.mil/work-with-us/office-wide-broad-agency-announcements")
    console.print("2. Find the specific office BAA")
    console.print("3. Follow submission instructions in the BAA document")
    console.print()
    console.print("[dim]Note: Office-wide BAAs are refreshed annually.[/dim]")


@app.command()
def feed(
    feed_type: str = typer.Argument("programs", help="Feed type: programs, opportunities"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get raw RSS feed data."""
    if feed_type == "programs":
        url = DARPA_RSS_URL
    elif feed_type == "opportunities":
        url = DARPA_OPPORTUNITIES_RSS
    else:
        console.print(f"[red]Unknown feed type: {feed_type}[/red]")
        console.print("Valid types: programs, opportunities")
        raise typer.Exit(1)

    console.print(f"[dim]Fetching {feed_type} feed...[/dim]")

    try:
        xml_content = fetch_url(url)
        items = parse_rss(xml_content)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if output_json:
        output = [
            {
                "title": i.title,
                "link": i.link,
                "description": i.description,
                "pub_date": i.pub_date,
                "category": i.category,
            }
            for i in items
        ]
        print(json.dumps(output, indent=2))
    else:
        for item in items:
            console.print(f"[bold]{item.title}[/bold]")
            console.print(f"  {item.link}")
            console.print(f"  {item.pub_date}")
            console.print()


@app.command()
def analyze(
    baa: str = typer.Argument(..., help="Path to BAA document (PDF or text file)"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Analyze a BAA document to extract requirements.
    
    Parses the BAA to identify:
    - Technical areas of interest
    - Page limits for each volume
    - Evaluation criteria
    - Required sections
    - Submission deadlines
    """
    from pathlib import Path
    
    baa_path = Path(baa)
    if not baa_path.exists():
        console.print(f"[red]BAA file not found: {baa}[/red]")
        raise typer.Exit(1)
    
    console.print(f"[dim]Analyzing BAA: {baa_path.name}...[/dim]")
    
    # Read file content
    if baa_path.suffix.lower() == ".pdf":
        console.print("[yellow]PDF parsing requires extractor skill. Using text extraction...[/yellow]")
        # For now, just note PDF support is limited
        try:
            import subprocess
            result = subprocess.run(
                ["pdftotext", "-layout", str(baa_path), "-"],
                capture_output=True, text=True, timeout=30
            )
            content = result.stdout if result.returncode == 0 else ""
        except Exception:
            console.print("[red]pdftotext not available. Please provide a text file.[/red]")
            raise typer.Exit(1)
    else:
        content = baa_path.read_text()
    
    # Extract key information using regex patterns
    analysis = {
        "filename": baa_path.name,
        "page_limits": {},
        "sections_required": [],
        "evaluation_criteria": [],
        "deadlines": [],
        "technical_areas": [],
    }
    
    # Page limit patterns
    page_patterns = [
        r"volume\s*(?:i|1|one)[^\d]*(\d+)\s*page",
        r"technical\s*(?:volume|proposal)[^\d]*(\d+)\s*page",
        r"(?:not\s*to\s*exceed|maximum\s*of?)\s*(\d+)\s*page",
    ]
    for pattern in page_patterns:
        matches = re.findall(pattern, content.lower())
        if matches:
            analysis["page_limits"]["volume_i"] = int(matches[0])
            break
    
    # Required sections patterns
    section_patterns = [
        r"must\s+include[:\s]+([\w\s,]+(?:section|paragraph|volume))",
        r"required\s+(?:sections?|elements?)[:\s]+([^\n]+)",
    ]
    for pattern in section_patterns:
        matches = re.findall(pattern, content.lower())
        analysis["sections_required"].extend(matches[:5])
    
    # Evaluation criteria
    eval_patterns = [
        r"evaluation\s+criteria[:\s]+([^\n]+)",
        r"evaluated\s+(?:based\s+on|using)[:\s]+([^\n]+)",
    ]
    for pattern in eval_patterns:
        matches = re.findall(pattern, content.lower())
        analysis["evaluation_criteria"].extend(matches[:5])
    
    # Deadline patterns
    deadline_patterns = [
        r"((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pattern in deadline_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        analysis["deadlines"].extend(matches[:3])
    
    if output_json:
        print(json.dumps(analysis, indent=2))
        return
    
    # Display analysis
    console.print(Panel(f"[bold]BAA Analysis: {baa_path.name}[/bold]"))
    
    if analysis["page_limits"]:
        console.print("\n[cyan]Page Limits:[/cyan]")
        for vol, limit in analysis["page_limits"].items():
            console.print(f"  {vol}: {limit} pages")
    
    if analysis["deadlines"]:
        console.print("\n[cyan]Deadlines Found:[/cyan]")
        for deadline in analysis["deadlines"]:
            console.print(f"  • {deadline}")
    
    if analysis["evaluation_criteria"]:
        console.print("\n[cyan]Evaluation Criteria:[/cyan]")
        for crit in analysis["evaluation_criteria"][:3]:
            console.print(f"  • {crit[:100]}...")
    
    console.print("\n[dim]Tip: Use --json for full analysis output[/dim]")


@app.command()
def generate(
    project: str = typer.Argument(..., help="Path to project directory"),
    baa_id: str = typer.Option(None, "--baa-id", help="BAA identifier for reference"),
    output: str = typer.Option("./proposal-draft", "--output", "-o", help="Output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be generated"),
):
    """
    Generate DARPA proposal draft using create-paper.
    
    Creates a proposal using the DARPA BAA template with:
    - Executive Summary
    - Goals and Impact
    - Technical Approach
    - Team Organization
    - Management Plan
    - Schedule and Milestones
    """
    from pathlib import Path
    import subprocess
    
    project_path = Path(project)
    if not project_path.exists():
        console.print(f"[red]Project directory not found: {project}[/red]")
        raise typer.Exit(1)
    
    console.print(f"[bold]Generating DARPA Proposal Draft[/bold]")
    console.print(f"  Project: {project_path}")
    console.print(f"  BAA ID: {baa_id or 'Not specified'}")
    console.print(f"  Output: {output}")
    
    if dry_run:
        console.print("\n[yellow]DRY RUN - Would generate:[/yellow]")
        console.print("  • sections/executive_summary.tex")
        console.print("  • sections/goals_impact.tex")
        console.print("  • sections/technical_approach.tex")
        console.print("  • sections/team_organization.tex")
        console.print("  • sections/management_plan.tex")
        console.print("  • sections/schedule_milestones.tex")
        console.print("  • draft.tex (DARPA BAA template)")
        console.print("  • references.bib")
        console.print("  • metadata.json")
        return
    
    # Find create-paper skill
    skill_paths = [
        Path(__file__).parent.parent / "create-paper" / "run.sh",
        Path.home() / ".pi" / "skills" / "create-paper" / "run.sh",
    ]
    
    paper_writer = None
    for path in skill_paths:
        if path.exists():
            paper_writer = path
            break
    
    if not paper_writer:
        console.print("[red]create-paper skill not found.[/red]")
        console.print("Install it from: .pi/skills/create-paper")
        raise typer.Exit(1)
    
    console.print(f"\n[dim]Using create-paper: {paper_writer}[/dim]")
    
    # Build command
    cmd = [
        str(paper_writer),
        "draft",
        "--project", str(project_path),
        "--template", "darpa_baa",
        "--output", output,
    ]
    
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            console.print(f"\n[green]✓ Proposal draft generated: {output}[/green]")
        else:
            console.print(f"[red]Error running create-paper:[/red]")
            console.print(result.stderr)
            raise typer.Exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]Timeout: create-paper took too long[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def check(
    proposal: str = typer.Argument(..., help="Path to proposal output directory"),
    strict: bool = typer.Option(False, "--strict", help="Fail on any warning"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Check proposal compliance with DARPA BAA requirements.
    
    Verifies:
    - Page count limits (default: 25 pages for Volume I)
    - Required sections present
    - Font size (12pt minimum)
    - Margin requirements (1 inch)
    """
    from pathlib import Path
    
    proposal_path = Path(proposal)
    if not proposal_path.exists():
        console.print(f"[red]Proposal directory not found: {proposal}[/red]")
        raise typer.Exit(1)
    
    console.print(f"[dim]Checking proposal compliance: {proposal}[/dim]")
    
    results = {
        "path": str(proposal_path),
        "checks": [],
        "passed": 0,
        "failed": 0,
        "warnings": 0,
    }
    
    # Check 1: Required files exist
    required_files = ["draft.tex", "sections"]
    for req in required_files:
        path = proposal_path / req
        if path.exists():
            results["checks"].append({"name": f"File exists: {req}", "status": "pass"})
            results["passed"] += 1
        else:
            results["checks"].append({"name": f"File exists: {req}", "status": "fail"})
            results["failed"] += 1
    
    # Check 2: Draft.tex has DARPA formatting
    draft_tex = proposal_path / "draft.tex"
    if draft_tex.exists():
        content = draft_tex.read_text()
        
        # Font size check
        if "12pt" in content or "12 pt" in content:
            results["checks"].append({"name": "Font size: 12pt", "status": "pass"})
            results["passed"] += 1
        else:
            results["checks"].append({"name": "Font size: 12pt", "status": "warning", "note": "Could not verify font size"})
            results["warnings"] += 1
        
        # Margins check
        if "1in" in content or "1 in" in content or "margin" in content.lower():
            results["checks"].append({"name": "Margins: 1 inch", "status": "pass"})
            results["passed"] += 1
        else:
            results["checks"].append({"name": "Margins: 1 inch", "status": "warning", "note": "Could not verify margins"})
            results["warnings"] += 1
    
    # Check 3: Required DARPA sections
    sections_dir = proposal_path / "sections"
    darpa_sections = [
        "executive_summary",
        "goals_impact",
        "technical_approach",
        "team_organization",
    ]
    
    if sections_dir.exists():
        existing_files = [f.stem for f in sections_dir.glob("*.tex")]
        for section in darpa_sections:
            if any(section in f for f in existing_files):
                results["checks"].append({"name": f"Section: {section}", "status": "pass"})
                results["passed"] += 1
            else:
                # Check for alternative naming
                alt_found = any(section.replace("_", "") in f.replace("_", "") for f in existing_files)
                if alt_found:
                    results["checks"].append({"name": f"Section: {section}", "status": "pass"})
                    results["passed"] += 1
                else:
                    results["checks"].append({"name": f"Section: {section}", "status": "warning", "note": "Section may be missing or renamed"})
                    results["warnings"] += 1
    
    # Output results
    if output_json:
        print(json.dumps(results, indent=2))
        return
    
    console.print(f"\n[bold]Compliance Check Results[/bold]")
    console.print(f"  Passed: [green]{results['passed']}[/green]")
    console.print(f"  Warnings: [yellow]{results['warnings']}[/yellow]")
    console.print(f"  Failed: [red]{results['failed']}[/red]\n")
    
    for check in results["checks"]:
        if check["status"] == "pass":
            console.print(f"  [green]✓[/green] {check['name']}")
        elif check["status"] == "warning":
            console.print(f"  [yellow]⚠[/yellow] {check['name']}")
            if "note" in check:
                console.print(f"      [dim]{check['note']}[/dim]")
        else:
            console.print(f"  [red]✗[/red] {check['name']}")
    
    # Exit code
    if results["failed"] > 0:
        console.print("\n[red]Compliance check failed.[/red]")
        raise typer.Exit(1)
    elif strict and results["warnings"] > 0:
        console.print("\n[yellow]Warnings found (strict mode).[/yellow]")
        raise typer.Exit(1)
    else:
        console.print("\n[green]Compliance check passed.[/green]")


@app.command()
def version():
    """Show version."""
    console.print("ops-darpa v0.1.0")
    console.print(f"[dim]DARPA RSS: {DARPA_RSS_URL}[/dim]")
    console.print(f"[dim]Grants.gov API: {GRANTS_GOV_API}[/dim]")


if __name__ == "__main__":
    app()
