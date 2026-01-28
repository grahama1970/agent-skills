#!/usr/bin/env python3
"""
SAM.gov Operations Skill

Query the U.S. federal government's System for Award Management for:
- Entity registrations (contractors)
- Exclusions (debarments/suspensions)
- Opportunities (solicitations)
- Contract awards

API Documentation: https://open.gsa.gov/api/
"""

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

app = typer.Typer(help="SAM.gov federal contracts and entity operations")
console = Console()

# API Configuration
BASE_URL = "https://api.sam.gov"
ALPHA_URL = "https://api-alpha.sam.gov"

# API Endpoints
ENDPOINTS = {
    "entity": "/entity-information/v3/entities",
    "exclusions": "/entity-information/v4/exclusions",
    "opportunities": "/opportunities/v2/search",
}


def get_api_key() -> str:
    """Get SAM.gov API key from environment."""
    key = os.environ.get("SAMGOV_API_KEY")
    if not key:
        # Try loading from .env in workspace root
        env_paths = [
            Path.cwd() / ".env",
            Path(__file__).parent.parent.parent.parent / ".env",
        ]
        for env_path in env_paths:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("SAMGOV_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if key:
                break

    if not key:
        console.print("[red]SAMGOV_API_KEY not found.[/red]")
        console.print("Set in environment or .env file.")
        console.print("Get a key at: https://sam.gov (Account Details > Public API Key)")
        raise typer.Exit(1)

    return key


def get_base_url() -> str:
    """Get base URL (production or alpha)."""
    if os.environ.get("SAMGOV_USE_ALPHA", "").lower() == "true":
        return ALPHA_URL
    return BASE_URL


def api_request(
    endpoint: str,
    params: dict[str, Any],
    method: str = "GET",
) -> dict[str, Any]:
    """Make an API request to SAM.gov."""
    api_key = get_api_key()
    base_url = get_base_url()

    # Add API key
    params["api_key"] = api_key

    # Build URL
    url = f"{base_url}{endpoint}"
    if method == "GET":
        url = f"{url}?{urlencode(params)}"

    try:
        req = Request(url, method=method)
        req.add_header("Accept", "application/json")

        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            return data

    except HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        if e.code == 429:
            return {"error": "Rate limit exceeded. Try again later.", "code": 429}
        elif e.code == 401:
            return {"error": "Invalid API key", "code": 401}
        elif e.code == 403:
            return {"error": "Access denied. Check API key permissions.", "code": 403}
        else:
            return {"error": f"HTTP {e.code}: {error_body[:200]}", "code": e.code}

    except URLError as e:
        return {"error": f"Network error: {e.reason}"}

    except Exception as e:
        return {"error": str(e)}


@app.command()
def entity(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Business name to search"),
    uei: Optional[str] = typer.Option(None, "--uei", "-u", help="Unique Entity Identifier"),
    cage: Optional[str] = typer.Option(None, "--cage", "-c", help="CAGE code"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Registration status (active/expired)"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search SAM.gov entity registrations (government contractors)."""
    if not any([name, uei, cage]):
        console.print("[red]Provide at least one search parameter: --name, --uei, or --cage[/red]")
        raise typer.Exit(1)

    params: dict[str, Any] = {}

    if name:
        params["legalBusinessName"] = name
    if uei:
        params["ueiSAM"] = uei
    if cage:
        params["cageCode"] = cage
    if status:
        params["registrationStatus"] = "A" if status.lower() == "active" else "E"

    console.print(f"[dim]Searching SAM.gov entities...[/dim]")
    result = api_request(ENDPOINTS["entity"], params)

    if result.get("error"):
        console.print(f"[red]Error:[/red] {result['error']}")
        raise typer.Exit(1)

    entities = result.get("entityData", [])

    if output_json:
        print(json.dumps(entities, indent=2))
        return

    if not entities:
        console.print("[yellow]No entities found.[/yellow]")
        return

    console.print(f"[bold]Found {len(entities)} entities:[/bold]\n")

    for ent in entities[:limit]:
        info = ent.get("entityRegistration", {})
        core = ent.get("coreData", {})
        entity_info = core.get("entityInformation", {})

        uei_val = info.get("ueiSAM", "N/A")
        cage_val = info.get("cageCode", "N/A")
        legal_name = info.get("legalBusinessName", "Unknown")
        status_val = info.get("registrationStatus", "Unknown")
        expiration = info.get("registrationExpirationDate", "N/A")

        # Business types
        bus_types = entity_info.get("entityType", [])
        if isinstance(bus_types, list):
            bus_types_str = ", ".join(bus_types[:3])
        else:
            bus_types_str = str(bus_types) if bus_types else "N/A"

        # Address
        address = core.get("physicalAddress", {})
        addr_str = f"{address.get('city', '')}, {address.get('stateOrProvinceCode', '')} {address.get('countryCode', '')}"

        # Status badge
        status_badge = "[green]ACTIVE[/green]" if status_val == "Active" else "[red]EXPIRED[/red]"

        console.print(Panel(
            f"[bold]{legal_name}[/bold] {status_badge}\n\n"
            f"[cyan]UEI:[/cyan] {uei_val}\n"
            f"[cyan]CAGE:[/cyan] {cage_val}\n"
            f"[cyan]Expires:[/cyan] {expiration}\n"
            f"[cyan]Types:[/cyan] {bus_types_str}\n"
            f"[cyan]Location:[/cyan] {addr_str}",
            title="Entity Registration",
        ))


@app.command()
def exclusions(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Name to search (individual or firm)"),
    uei: Optional[str] = typer.Option(None, "--uei", "-u", help="UEI to check"),
    classification: Optional[str] = typer.Option(None, "--classification", "-c", help="Firm/Individual/Vessel"),
    agency: Optional[str] = typer.Option(None, "--agency", "-a", help="Excluding agency code (DOJ, DLA, AF, etc.)"),
    state: Optional[str] = typer.Option(None, "--state", "-s", help="State code (VA, CA, etc.)"),
    active_only: bool = typer.Option(False, "--active-only", help="Only show active exclusions"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search SAM.gov exclusions list (debarments/suspensions)."""
    params: dict[str, Any] = {}

    if name:
        params["q"] = name
    if uei:
        params["ueiSAM"] = uei
    if classification:
        params["classification"] = classification
    if agency:
        params["excludingAgencyCode"] = agency
    if state:
        params["stateProvince"] = state

    console.print(f"[dim]Searching SAM.gov exclusions...[/dim]")
    result = api_request(ENDPOINTS["exclusions"], params)

    if result.get("error"):
        console.print(f"[red]Error:[/red] {result['error']}")
        raise typer.Exit(1)

    exclusions_list = result.get("results", [])

    # Filter active only if requested
    if active_only:
        exclusions_list = [
            e for e in exclusions_list
            if e.get("exclusionDetails", {}).get("exclusionStatus") == "Active"
        ]

    if output_json:
        print(json.dumps(exclusions_list, indent=2))
        return

    if not exclusions_list:
        console.print("[green]No exclusions found.[/green]")
        return

    console.print(f"[bold red]Found {len(exclusions_list)} exclusions:[/bold red]\n")

    for exc in exclusions_list[:limit]:
        details = exc.get("exclusionDetails", {})
        ident = exc.get("exclusionIdentification", {})
        actions = exc.get("exclusionActions", {})
        address = exc.get("exclusionAddress", {})

        name_val = ident.get("name", "Unknown")
        classification_val = details.get("classificationType", "N/A")
        exc_type = details.get("exclusionType", "N/A")
        status_val = details.get("exclusionStatus", "N/A")
        excluding_agency = actions.get("excludingAgency", "N/A")

        # Dates
        active_date = actions.get("activeDate", "N/A")
        term_date = actions.get("terminationDate", "N/A")

        # Address
        addr_str = f"{address.get('city', '')}, {address.get('stateOrProvince', '')} {address.get('country', '')}"

        # Status badge
        status_badge = "[red]ACTIVE[/red]" if status_val == "Active" else "[yellow]INACTIVE[/yellow]"

        console.print(Panel(
            f"[bold]{name_val}[/bold] {status_badge}\n\n"
            f"[cyan]Classification:[/cyan] {classification_val}\n"
            f"[cyan]Type:[/cyan] {exc_type}\n"
            f"[cyan]Agency:[/cyan] {excluding_agency}\n"
            f"[cyan]Active Date:[/cyan] {active_date}\n"
            f"[cyan]Termination:[/cyan] {term_date}\n"
            f"[cyan]Location:[/cyan] {addr_str}",
            title="Exclusion Record",
            border_style="red",
        ))


@app.command()
def opportunities(
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Search keyword"),
    naics: Optional[str] = typer.Option(None, "--naics", "-n", help="NAICS code"),
    ptype: Optional[str] = typer.Option(None, "--type", "-t", help="Procurement type (p/o/a/r/s/k/u)"),
    set_aside: Optional[str] = typer.Option(None, "--set-aside", help="Set-aside type"),
    days: int = typer.Option(30, "--days", "-d", help="Search last N days"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search SAM.gov contract opportunities (solicitations)."""
    # Calculate date range
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    params: dict[str, Any] = {
        "postedFrom": from_date.strftime("%m/%d/%Y"),
        "postedTo": to_date.strftime("%m/%d/%Y"),
        "limit": min(limit, 1000),
    }

    if keyword:
        params["title"] = keyword
    if naics:
        params["ncode"] = naics
    if ptype:
        params["ptype"] = ptype
    if set_aside:
        params["typeOfSetAside"] = set_aside

    console.print(f"[dim]Searching SAM.gov opportunities (last {days} days)...[/dim]")
    result = api_request(ENDPOINTS["opportunities"], params)

    if result.get("error"):
        console.print(f"[red]Error:[/red] {result['error']}")
        raise typer.Exit(1)

    opps = result.get("opportunitiesData", [])

    if output_json:
        print(json.dumps(opps, indent=2))
        return

    if not opps:
        console.print("[yellow]No opportunities found.[/yellow]")
        return

    console.print(f"[bold]Found {len(opps)} opportunities:[/bold]\n")

    table = Table(title="Contract Opportunities")
    table.add_column("Sol #", style="cyan", width=15)
    table.add_column("Title", width=40)
    table.add_column("Type", width=10)
    table.add_column("Posted", width=12)
    table.add_column("Response", width=12)

    for opp in opps[:limit]:
        sol_num = opp.get("solicitationNumber", "N/A")[:15]
        title = opp.get("title", "Unknown")[:38]
        opp_type = opp.get("type", "N/A")
        posted = opp.get("postedDate", "N/A")[:10]
        response = opp.get("responseDeadLine", "N/A")[:10] if opp.get("responseDeadLine") else "Open"

        table.add_row(sol_num, title, opp_type, posted, response)

    console.print(table)

    console.print("\n[dim]View details at: https://sam.gov/opp/<solicitation_number>[/dim]")


@app.command()
def check(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Entity name to verify"),
    uei: Optional[str] = typer.Option(None, "--uei", "-u", help="UEI to verify"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Quick verification: Check if entity is registered AND not excluded.

    Combines entity lookup and exclusions check in one command.
    """
    if not any([name, uei]):
        console.print("[red]Provide --name or --uei to check[/red]")
        raise typer.Exit(1)

    results = {
        "query": {"name": name, "uei": uei},
        "entity": None,
        "exclusions": [],
        "status": "unknown",
    }

    console.print(f"[bold]Verifying entity...[/bold]\n")

    # Check entity registration
    entity_params: dict[str, Any] = {}
    if name:
        entity_params["legalBusinessName"] = name
    if uei:
        entity_params["ueiSAM"] = uei

    console.print("[dim]1. Checking entity registration...[/dim]")
    entity_result = api_request(ENDPOINTS["entity"], entity_params)

    entities = entity_result.get("entityData", [])
    if entities:
        results["entity"] = entities[0]
        reg_status = entities[0].get("entityRegistration", {}).get("registrationStatus", "Unknown")
        console.print(f"   [green]Found:[/green] {entities[0].get('entityRegistration', {}).get('legalBusinessName', 'Unknown')}")
        console.print(f"   Registration: {reg_status}")
    else:
        console.print("   [yellow]No registration found[/yellow]")

    # Check exclusions
    excl_params: dict[str, Any] = {}
    if name:
        excl_params["q"] = name
    if uei:
        excl_params["ueiSAM"] = uei

    console.print("\n[dim]2. Checking exclusions list...[/dim]")
    excl_result = api_request(ENDPOINTS["exclusions"], excl_params)

    exclusions_list = excl_result.get("results", [])
    active_exclusions = [
        e for e in exclusions_list
        if e.get("exclusionDetails", {}).get("exclusionStatus") == "Active"
    ]

    results["exclusions"] = exclusions_list

    if active_exclusions:
        console.print(f"   [red]WARNING: {len(active_exclusions)} active exclusion(s) found![/red]")
        results["status"] = "excluded"
        for exc in active_exclusions[:3]:
            exc_name = exc.get("exclusionIdentification", {}).get("name", "Unknown")
            exc_type = exc.get("exclusionDetails", {}).get("exclusionType", "N/A")
            console.print(f"   - {exc_name}: {exc_type}")
    else:
        console.print("   [green]No active exclusions[/green]")
        if entities:
            results["status"] = "verified"

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    if results["status"] == "verified":
        console.print("[green]Entity is registered and not excluded.[/green]")
    elif results["status"] == "excluded":
        console.print("[red]Entity has active exclusions - DO NOT AWARD.[/red]")
    else:
        console.print("[yellow]Could not fully verify entity status.[/yellow]")

    if output_json:
        print(json.dumps(results, indent=2, default=str))


@app.command()
def version():
    """Show version and API key status."""
    console.print("sam-gov-ops v0.1.0")

    try:
        key = get_api_key()
        masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
        console.print(f"[green]API Key:[/green] {masked}")
        console.print(f"[dim]Base URL: {get_base_url()}[/dim]")
    except typer.Exit:
        console.print("[red]API Key: Not configured[/red]")


if __name__ == "__main__":
    app()
