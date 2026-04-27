"""CLI for saved /ask review-chain specs."""

from __future__ import annotations

import json

import typer

from .chain_specs import get_chain_spec, load_chain_specs, validate_chain_spec

app = typer.Typer(help="/ask chains - Inspect saved review chains")


@app.command()
def list(
    as_json: bool = typer.Option(False, "--json", help="Emit JSON"),
) -> None:
    chains = load_chain_specs()
    payload = {
        "chains": [
            {
                "name": name,
                "description": spec.get("description", ""),
                "path": spec.get("path", ""),
                "valid": not validate_chain_spec(spec),
                "stages": [stage.get("name", "") for stage in spec.get("stages", [])],
            }
            for name, spec in sorted(chains.items())
        ]
    }
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for chain in payload["chains"]:
        status = "valid" if chain["valid"] else "invalid"
        print(f"- {chain['name']} ({status}): {chain['description']}")
        print(f"  path: {chain['path']}")
        print(f"  stages: {', '.join(chain['stages'])}")


@app.command()
def show(
    name: str = typer.Argument(..., help="Chain name"),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON"),
) -> None:
    spec = get_chain_spec(name)
    if as_json:
        print(json.dumps(spec, indent=2, sort_keys=True))
        return
    print(f"{spec['name']}: {spec.get('description', '')}")
    print(f"path: {spec.get('path', '')}")
    for stage in spec.get("stages", []):
        print(f"- {stage.get('name')}: {stage.get('type')}")


@app.command()
def validate(
    as_json: bool = typer.Option(False, "--json", help="Emit JSON"),
) -> None:
    chains = load_chain_specs()
    results = {
        name: validate_chain_spec(spec)
        for name, spec in sorted(chains.items())
    }
    ok = all(not errors for errors in results.values())
    payload = {"ok": ok, "results": results}
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("valid" if ok else "invalid")
        for name, errors in results.items():
            print(f"- {name}: {'ok' if not errors else '; '.join(errors)}")
    raise typer.Exit(code=0 if ok else 1)


if __name__ == "__main__":
    app()
