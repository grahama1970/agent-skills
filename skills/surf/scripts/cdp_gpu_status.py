#!/usr/bin/env python3
"""Report whether a running CDP browser is using hardware rendering."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def classify_gpu(gpu: dict) -> str:
    devices = gpu.get("devices") or []
    device = devices[0] if devices else {}
    aux = gpu.get("auxAttributes") or {}
    renderer = " ".join(
        str(value)
        for value in (
            device.get("vendorString"),
            device.get("deviceString"),
            device.get("driverVendor"),
            aux.get("displayType"),
            aux.get("glRenderer"),
            aux.get("glImplementationParts"),
        )
        if value
    ).lower()
    if any(marker in renderer for marker in ("swiftshader", "swangle", "llvmpipe")):
        return "software"
    if devices and renderer:
        return "hardware"
    return "unknown"


def fetch_system_info(port: int) -> dict:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client is not installed") from exc

    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/version", timeout=3
    ) as response:
        version = json.load(response)

    ws = websocket.create_connection(version["webSocketDebuggerUrl"], timeout=5)
    try:
        ws.send(json.dumps({"id": 1, "method": "SystemInfo.getInfo"}))
        while True:
            message = json.loads(ws.recv())
            if message.get("id") == 1:
                if "error" in message:
                    raise RuntimeError(message["error"].get("message", "CDP error"))
                return message["result"]
    finally:
        ws.close()


def build_report(system_info: dict) -> dict:
    gpu = system_info.get("gpu") or {}
    devices = gpu.get("devices") or []
    device = devices[0] if devices else {}
    aux = gpu.get("auxAttributes") or {}
    return {
        "renderer_mode": classify_gpu(gpu),
        "vendor": device.get("vendorString", ""),
        "device": device.get("deviceString", ""),
        "display_type": aux.get("displayType", ""),
        "gpu_compositing": (gpu.get("featureStatus") or {}).get(
            "gpu_compositing", "unknown"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9222)
    args = parser.parse_args()
    try:
        report = build_report(fetch_system_info(args.port))
    except Exception as exc:
        print(json.dumps({"renderer_mode": "unknown", "error": str(exc)}))
        return 3

    print(json.dumps(report))
    return 0 if report["renderer_mode"] == "hardware" else 2


if __name__ == "__main__":
    sys.exit(main())
