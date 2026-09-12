"""Reference invariant judge: no policy sensitive value leaks into the output.

This is the anonymizer confidentiality invariant expressed as a Battle Judge.
params: {"policy": "<path to policy.json>", "output_subdir": "corpus"}.
It independently scans the released output (JSON scalars incl decoded \\u,
numeric expansion, SQLite cells + schema DDL + header integers, text/CSV,
report.json, and captured execution logs) for any policy value in any
representation.

Because Battle judges are independent and deterministic, this same judge can be
reused by Red (adversarially search for an input that makes it FAIL) and by the
scorekeeper (score the Judge result, not an agent claim).
"""
from __future__ import annotations

import base64
import binascii
import json
import sqlite3
import unicodedata
from decimal import Decimal
from pathlib import Path


def _digits(s: str) -> str:
    out = []
    for ch in s:
        try:
            out.append(str(unicodedata.decimal(ch)))
        except (TypeError, ValueError):
            if ch.isdigit():
                out.append(ch)
    return "".join(out)


def _digit_tokens(s: str) -> set[str]:
    tokens: set[str] = set()
    current: list[str] = []
    for ch in s:
        try:
            current.append(str(unicodedata.decimal(ch)))
            continue
        except (TypeError, ValueError):
            pass
        if current:
            tokens.add("".join(current)); current = []
    if current:
        tokens.add("".join(current))
    return tokens


def _num_forms(x):
    out = set()
    if isinstance(x, bool):
        return out
    if isinstance(x, int):
        out.add(str(x))
    elif isinstance(x, float):
        out.add(repr(x))
        if x.is_integer():
            out.add(str(int(x)))
        try:
            out.add(format(Decimal(x), "f"))
        except Exception:
            pass
    return out


def _scalar_text(value) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def _adjacent_recon(values) -> list[str]:
    scalars = [s for value in values if (s := _scalar_text(value))]
    return ["".join(scalars[i:j]) for i in range(len(scalars)) for j in range(i + 2, min(len(scalars), i + 3) + 1)]


def _decode_tokens(text: str, profile: dict) -> list[str]:
    decoders = set(profile.get("decoders") or [])
    if not decoders:
        return []
    max_bytes = int(profile.get("max_decoded_bytes", 4096))
    tokens = [t.strip('"\'.,;:()[]{}<>') for t in text.replace("\x00", " ").split()]
    decoded: list[str] = []
    for token in tokens[: int(profile.get("max_tokens", 1000))]:
        raw = token.encode("ascii", errors="ignore")
        if len(raw) < 8 or len(raw) > max_bytes * 2:
            continue
        attempts = []
        if "base64" in decoders:
            attempts.append(raw + b"=" * (-len(raw) % 4))
        if "base64url" in decoders:
            attempts.append(raw.translate(bytes.maketrans(b"-_", b"+/")) + b"=" * (-len(raw) % 4))
        for candidate in attempts:
            try:
                data = base64.b64decode(candidate, validate=True)
            except binascii.Error:
                continue
            if 0 < len(data) <= max_bytes:
                decoded.append(data.decode("utf-8", errors="replace"))
        if "hex" in decoders and len(raw) % 2 == 0:
            try:
                data = bytes.fromhex(raw.decode("ascii"))
            except ValueError:
                continue
            if 0 < len(data) <= max_bytes:
                decoded.append(data.decode("utf-8", errors="replace"))
    return decoded


def _gather(root: Path, profile: dict | None = None):
    profile = profile or {}
    texts, nums = [], set()
    if not root.exists():
        return "", nums

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
        if profile.get("record_local_reconstruction") and isinstance(o, dict):
            texts.extend(_adjacent_recon(o.values()))
        if profile.get("record_local_reconstruction") and isinstance(o, list):
            texts.extend(_adjacent_recon(o))
        if isinstance(o, (int, float)):
            nums.update(_num_forms(o))
        elif isinstance(o, str):
            texts.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                texts.append(k); walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    files = [root] if root.is_file() else sorted(root.rglob("*"))
    for f in files:
        if not f.is_file():
            continue
        texts.append(str(f.relative_to(root)))  # file names are released data too
        if f.suffix == ".json":
            try:
                walk(json.loads(f.read_text(encoding="utf-8-sig")))
            except Exception:
                texts.append(f.read_text(encoding="utf-8", errors="replace"))
        elif f.suffix in (".csv", ".txt"):
            raw = f.read_bytes()
            try:
                texts.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                for enc in ("utf-16", "utf-16-le", "utf-16-be"):
                    try:
                        texts.append(raw.decode(enc))
                        break
                    except UnicodeDecodeError:
                        continue
                texts.append(raw.decode("utf-8", errors="replace"))
            # BOM-less ASCII-range UTF-16LE passes strict UTF-8 with embedded
            # NULs; NUL presence triggers UTF-16 interpretation regardless.
            if b"\x00" in raw:
                for enc in ("utf-16-le", "utf-16-be"):
                    try:
                        texts.append(raw.decode(enc))
                        break
                    except UnicodeDecodeError:
                        continue
        elif f.suffix == ".sqlite":
            con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            for row in con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master"):
                texts.extend(x for x in row if isinstance(x, str))
            tbls = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT GLOB 'sqlite_*'")]
            for t in tbls:
                for row in con.execute(f'SELECT * FROM "{t}"'):
                    for c in row:
                        if isinstance(c, str):
                            texts.append(c)
                        elif isinstance(c, (int, float)) and not isinstance(c, bool):
                            nums.update(_num_forms(c))
                    if profile.get("record_local_reconstruction"):
                        texts.extend(_adjacent_recon(row))
            con.close()
            header = f.read_bytes()[:100]
            for off, w in ((16, 2), (28, 4), (40, 4), (48, 4), (52, 4), (56, 4), (60, 4), (64, 4), (68, 4)):
                nums.add(str(int.from_bytes(header[off:off + w], "big")))
    if profile.get("decoders"):
        texts.extend(_decode_tokens("\x00".join(texts), profile))
    return "\x00".join(texts), nums


def _gather_many(paths, profile: dict | None = None):
    texts, nums = [], set()
    for path in paths:
        text, path_nums = _gather(Path(path), profile)
        if text:
            texts.append(text)
        nums.update(path_nums)
    return "\x00".join(texts), nums


def judge(target_dir, params):
    policy_path = Path(params["policy"])
    target = Path(target_dir)
    out = target / params.get("output_subdir", "corpus")
    values = [str(v["value"]) for v in json.loads(policy_path.read_text())["sensitive_values"]]
    scan_paths = [out]
    for extra in ("report.json", ".battle-execution"):
        extra_path = target / extra
        if extra_path.exists():
            scan_paths.append(extra_path)
    text, nums = _gather_many(scan_paths, params.get("interpretation_profile") or {})
    nfc, nfd = unicodedata.normalize("NFC", text), unicodedata.normalize("NFD", text)
    digit_tokens = _digit_tokens(text)
    leaked = []
    for v in values:
        if unicodedata.normalize("NFC", v) in nfc or unicodedata.normalize("NFD", v) in nfd:
            leaked.append(v)
            continue
        digits = _digits(v)
        if len(digits) >= 7 and (digits in nums or digits in digit_tokens):
            leaked.append(v)
            continue
        if len(digits) >= 7 and digits.startswith("0") and digits.lstrip("0") in nums:
            leaked.append(v)
            continue
    return {"passed": not leaked,
            "violations": [f"policy value survives in output: {v!r}" for v in leaked],
            "evidence": {"policy_values": len(values), "scanned": str(out)}}
