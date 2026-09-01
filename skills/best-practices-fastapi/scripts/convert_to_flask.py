#!/usr/bin/env python3
"""Generate a thin Flask adapter from a validated route manifest."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RouteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(min_length=1)
    request_model: str | None = None
    response_model: str = Field(min_length=1)
    service_call: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def name_is_identifier(cls, value: str) -> str:
        if not value.isidentifier():
            raise ValueError("route name must be a Python identifier")
        return value

    @field_validator("path")
    @classmethod
    def path_is_absolute(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("route path must start with /")
        return value

    @field_validator("service_call")
    @classmethod
    def service_call_shape(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 2 or not all(part.isidentifier() for part in parts):
            raise ValueError("service_call must look like module.function")
        return value


class RouteManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["best_practices_fastapi.route_manifest.v1"] = Field(alias="schema")
    module: str = Field(default="app")
    routes: list[RouteSpec] = Field(min_length=1)


def load_manifest(path: Path) -> RouteManifest:
    return RouteManifest.model_validate_json(path.read_text())


def render_flask(manifest: RouteManifest) -> str:
    route_blocks: list[str] = []
    for route in manifest.routes:
        service_module, service_func = route.service_call.split(".")
        load_payload = "payload = None"
        call_arg = ""
        if route.request_model:
            load_payload = (
                "payload = contracts.{model}.model_validate(request.get_json(force=True) or {{}})"
                .format(model=route.request_model)
            )
            call_arg = "payload"
        route_blocks.append(
            f"@app.route({route.path!r}, methods=[{route.method!r}])\n"
            f"def {route.name}():\n"
            f"    {load_payload}\n"
            f"    result = {service_module}.{service_func}({call_arg})\n"
            f"    if hasattr(result, '__await__'):\n"
            f"        raise RuntimeError('Flask fallback needs a sync service facade for async work')\n"
            f"    response = contracts.{route.response_model}.model_validate(result)\n"
            f"    return jsonify(response.model_dump(mode='json'))\n"
        )
    return (
        '"""Generated Flask fallback adapter. Business logic stays outside Flask."""\n'
        "from __future__ import annotations\n\n"
        "from flask import Flask, jsonify, request\n\n"
        "try:\n"
        "    from . import contracts, service\n"
        "except ImportError:  # pragma: no cover - direct script smoke use\n"
        "    import contracts, service\n\n"
        "app = Flask(__name__)\n\n"
        + "\n".join(route_blocks)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(render_flask(manifest))
    except Exception as exc:
        print(f"manifest validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"schema": "best_practices_fastapi.convert_to_flask.v1", "status": "PASS", "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
