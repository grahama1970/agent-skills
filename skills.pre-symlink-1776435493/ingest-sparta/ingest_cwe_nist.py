#!/usr/bin/env python3
"""
Ingest CWE→NIST SP 800-53 mappings from MITRE Heimdall.

This enables the 2-hop crosswalk path: CWE → NIST → SV (via tor_threats)

Data source: MITRE Heimdall CWE-NIST mapping CSV
  https://raw.githubusercontent.com/mitre/heimdall_tools/master/lib/data/cwe-nist-mapping.csv

Storage:
  - CSV cached at /mnt/storage12tb/cwe/cwe-nist-mapping.csv
  - Field `nist_control_ids` added to CWE docs in sparta_controls
  - Field `nist_source` set to "mitre_heimdall_800-53r4" for provenance

Usage:
  python ingest_cwe_nist.py [--download]  # Download fresh CSV from MITRE
  python ingest_cwe_nist.py               # Use cached CSV

Note: This is a one-time ingestion. Re-running will update existing mappings.
MITRE Heimdall uses NIST SP 800-53 Rev 4 controls.
"""

import argparse
import csv
import httpx
import subprocess
from collections import defaultdict
from pathlib import Path

CSV_URL = "https://raw.githubusercontent.com/mitre/heimdall_tools/master/lib/data/cwe-nist-mapping.csv"
CSV_PATH = Path("/mnt/storage12tb/cwe/cwe-nist-mapping.csv")
SOCKET_PATH = "/run/user/1000/embry/memory.sock"


def download_csv():
    """Download fresh CSV from MITRE Heimdall."""
    print(f"Downloading from {CSV_URL}...")
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["wget", "-q", CSV_URL, "-O", str(CSV_PATH)], check=True)
    print(f"Saved to {CSV_PATH}")


def parse_csv() -> dict[str, list[str]]:
    """Parse CWE→NIST mappings from CSV."""
    cwe_to_nist = defaultdict(list)

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cwe_id = f"CWE-{row['CWE-ID'].strip()}"
            nist_id = row['NIST-ID'].strip()
            if nist_id and nist_id not in cwe_to_nist[cwe_id]:
                cwe_to_nist[cwe_id].append(nist_id)

    return dict(cwe_to_nist)


def ingest_to_sparta(cwe_to_nist: dict[str, list[str]]):
    """Upsert nist_control_ids to CWE docs in sparta_controls."""
    transport = httpx.HTTPTransport(uds=SOCKET_PATH)
    client = httpx.Client(transport=transport, base_url="http://localhost", timeout=120)

    # Find existing CWE docs
    cwe_ids = list(cwe_to_nist.keys())
    existing_cwes = {}

    batch_size = 50
    for i in range(0, len(cwe_ids), batch_size):
        batch = cwe_ids[i:i+batch_size]
        resp = client.post("/recall/by-keys", json={
            "keys": batch,
            "key_field": "control_id",
            "collection": "sparta_controls"
        })
        docs = resp.json().get("documents", [])
        for doc in docs:
            existing_cwes[doc.get("control_id")] = doc.get("_key")

    print(f"CWEs in sparta_controls: {len(existing_cwes)}/{len(cwe_ids)}")

    # Prepare updates
    docs_to_update = [
        {
            "_key": _key,
            "nist_control_ids": cwe_to_nist[cwe_id],
            "nist_source": "mitre_heimdall_800-53r4"
        }
        for cwe_id, _key in existing_cwes.items()
    ]

    # Batch upsert
    total_updated = 0
    for i in range(0, len(docs_to_update), 500):
        batch = docs_to_update[i:i+500]
        resp = client.post("/upsert", json={
            "collection": "sparta_controls",
            "documents": batch
        })
        if resp.status_code == 200:
            result = resp.json()
            total_updated += result.get("updated", 0)
        else:
            print(f"Error: {resp.text[:200]}")

    print(f"Updated: {total_updated} CWE docs")
    client.close()
    return total_updated


def verify():
    """Verify the 2-hop path works."""
    transport = httpx.HTTPTransport(uds=SOCKET_PATH)
    client = httpx.Client(transport=transport, base_url="http://localhost", timeout=60)

    # Test CWE-79 (XSS) → NIST → SV
    resp = client.post("/recall/by-keys", json={
        "keys": ["CWE-79"],
        "key_field": "control_id",
        "collection": "sparta_controls"
    })
    cwe_doc = resp.json().get("documents", [{}])[0]
    nist_ids = cwe_doc.get("nist_control_ids", [])

    if not nist_ids:
        print("Verification FAILED: CWE-79 has no nist_control_ids")
        return False

    # Hop 2: NIST → SV
    resp = client.post("/recall/by-keys", json={
        "keys": nist_ids,
        "key_field": "control_id",
        "collection": "sparta_controls"
    })
    nist_docs = resp.json().get("documents", [])

    sv_controls = set()
    for nist_doc in nist_docs:
        tor = nist_doc.get("tor_threats", []) or []
        sv_controls.update([t for t in tor if t.startswith("SV-")])

    print(f"\nVerification:")
    print(f"  CWE-79 → {nist_ids} → {len(sv_controls)} SV-* controls")
    print(f"  Sample SV-*: {sorted(sv_controls)[:5]}")

    client.close()
    return len(sv_controls) > 0


def main():
    parser = argparse.ArgumentParser(description="Ingest CWE→NIST mappings from MITRE Heimdall")
    parser.add_argument("--download", action="store_true", help="Download fresh CSV from MITRE")
    args = parser.parse_args()

    print("=" * 60)
    print("CWE→NIST SP 800-53 Ingestion (MITRE Heimdall)")
    print("=" * 60)

    # Download if requested or missing
    if args.download or not CSV_PATH.exists():
        download_csv()

    # Parse
    cwe_to_nist = parse_csv()
    print(f"\nParsed {len(cwe_to_nist)} CWE→NIST mappings")

    # Ingest
    print("\nIngesting to sparta_controls...")
    updated = ingest_to_sparta(cwe_to_nist)

    # Verify
    if updated > 0:
        verify()

    print("\nDone!")


if __name__ == "__main__":
    main()
