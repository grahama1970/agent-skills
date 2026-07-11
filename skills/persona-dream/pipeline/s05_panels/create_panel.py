#!/usr/bin/env python3
"""create-panel — contract-driven storyboard panel generator.

Reads a storyboard panel contract (produced by the upstream storyboard/script
step) and generates one panel image through the selected backend. The contract
drives the prompt so this script stays persona- and story-agnostic.

Backends:
  scillm      -> skills/create-image/run.sh (canonical receipt wrapper)
  nano-banana -> direct Fal.ai nano-banana call (FAL_KEY required)
"""
import sys
import json
import subprocess
import os
import argparse
from pathlib import Path

FAL_URL = os.environ.get("FAL_URL", "https://fal.run/fal-ai/nano-banana-2")

BACKENDS = {
    "scillm": {"model": "gpt-image-2"},
    "nano-banana": {"url": FAL_URL},
}
DEFAULT_BACKEND = "nano-banana"

DEFAULT_CONTRACT = Path(__file__).resolve().parents[2] / "fixtures" / "horus_embry" / "storyboard_panel_contract.json"


def load_contract(path: Path) -> dict:
    """Load and lightly validate a storyboard panel contract."""
    if not path.exists():
        raise ValueError(f"Contract not found: {path}")
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema") != "persona_dream.storyboard_panel_contract.v1":
        raise ValueError(f"Unsupported contract schema: {contract.get('schema')}")
    for required in ("look_lock", "characters", "panels"):
        if required not in contract:
            raise ValueError(f"Contract missing required field: {required}")
    return contract


def build_prompt(panel_num: str, contract: dict, extra: str | None = None) -> str:
    """Compose a panel-specific prompt from the storyboard contract."""
    panel = contract["panels"].get(panel_num)
    if panel is None:
        raise ValueError(f"Panel {panel_num} not defined in contract")

    size = contract.get("output_size", "1536x1024")
    aspect = contract.get("aspect_ratio", "16:9")

    parts = [
        f"Create a storyboard panel ({size}, {aspect}). {contract['look_lock']}. ",
        f"Shot: {panel['shot']}. ",
        "Characters must match approved reference sheets. ",
    ]

    if contract.get("props"):
        parts.append(f"Props: {contract['props']} ")
    if contract.get("environment"):
        parts.append(f"Environment: {contract['environment']} ")
    if contract.get("creatures"):
        parts.append(f"Creatures: {contract['creatures']} ")
    if contract.get("effects"):
        parts.append(f"Effects: {contract['effects']} ")

    # Include descriptions only for characters actually in this panel.
    characters = contract["characters"]
    for char_id in panel.get("characters", []):
        desc = characters.get(char_id)
        if desc:
            parts.append(f"{desc} ")

    if extra:
        parts.append(extra)

    return "".join(parts).strip()


def generate_panel(panel_num, output_path, contract_path=None, extra_prompt=None, backend=DEFAULT_BACKEND):
    contract_path = Path(contract_path or DEFAULT_CONTRACT)
    try:
        contract = load_contract(contract_path)
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

    try:
        prompt = build_prompt(panel_num, contract, extra_prompt)
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

    cfg = BACKENDS.get(backend, BACKENDS["scillm"])
    output_path = str(output_path)

    try:
        if backend == "nano-banana":
            import urllib.request
            fal_key = os.environ.get("FAL_KEY")
            if not fal_key:
                return {"status": "FAIL", "error": "FAL_KEY not set in environment"}
            body = json.dumps({"prompt": prompt, "aspect_ratio": "16:9", "resolution": "2K", "num_images": 1}).encode()
            req = urllib.request.Request(cfg["url"], data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Key {fal_key}"})
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())
            img_url = ""
            if result.get("data"):
                img_url = result["data"][0].get("url", "")
            elif result.get("images"):
                img_url = result["images"][0].get("url", "")
            if img_url:
                urllib.request.urlretrieve(img_url, output_path)
                return {"status": "PASS", "path": output_path, "backend": backend, "prompt": prompt[:200]}
            return {"status": "FAIL", "error": f"No image URL in {backend} response"}

        # scillm path: use the create-image skill wrapper so we get receipts,
        # Codex-OAuth handling, and the canonical scillm image generation flow.
        create_image_script = Path(__file__).resolve().parents[3] / "create-image" / "run.sh"
        if not create_image_script.exists():
            return {"status": "FAIL", "error": f"create-image wrapper not found: {create_image_script}"}

        size = contract.get("output_size", "1536x1024")
        cmd = [
            "bash", str(create_image_script),
            "generate",
            prompt,
            "--output", output_path,
            "--size", size,
            "--backend", "scillm",
            "--model", cfg["model"],
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            return {"status": "FAIL", "error": f"create-image failed: {res.stderr[-1200:]}"}
        if not Path(output_path).is_file() or Path(output_path).stat().st_size == 0:
            return {"status": "FAIL", "error": "create-image did not write output file"}
        return {"status": "PASS", "path": output_path, "backend": backend, "prompt": prompt[:200]}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", required=True, help="Panel ID from the contract")
    parser.add_argument("--output", required=True, help="Output PNG path")
    parser.add_argument("--contract", default=None, help="Path to storyboard panel contract JSON (default: Horus/Embry fixture)")
    parser.add_argument("--extra", default=None, help="Additional prompt text for corrections")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, choices=list(BACKENDS.keys()), help="Image generation backend")
    args = parser.parse_args()
    result = generate_panel(args.panel, args.output, args.contract, args.extra, args.backend)
    print(json.dumps(result))
    sys.exit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
