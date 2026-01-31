import hashlib
from typing import Optional

def generate_key(prefix: str, *parts: str) -> str:
    """Generate a stable, safe key from parts."""
    # Using hash for long/unsafe parts to keep key length manageable and safe
    raw = ":".join(str(p) for p in parts)
    seed = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{seed}"

def generate_rss_key(source_key: str, guid: Optional[str], link: str) -> str:
    # Prefer GUID, fallback to Link
    val = guid or link
    return generate_key("rss", source_key, val)

def generate_github_key(type: str, repo: str, id_or_num: str) -> str:
    # type: release, issue, disc
    # id_or_num: stable identifier
    return generate_key("gh", type, repo, str(id_or_num))

def generate_nvd_key(cve_id: str) -> str:
    return f"cve:{cve_id}" # Low collision risk, human readable
