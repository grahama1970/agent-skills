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
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path


_SQLITE_HEADER_INTEGER_FIELDS = (
    (16, 2),  # page size; encoded 1 means 65536
    (18, 1),  # file format write version
    (19, 1),  # file format read version
    (20, 1),  # reserved bytes per page
    (21, 1),  # maximum embedded payload fraction
    (22, 1),  # minimum embedded payload fraction
    (23, 1),  # leaf payload fraction
    (24, 4),  # file change counter
    (28, 4),  # database size in pages
    (32, 4),  # first freelist trunk page
    (36, 4),  # freelist page count
    (40, 4),  # schema cookie
    (44, 4),  # schema format number
    (48, 4),  # default page cache size
    (52, 4),  # largest root b-tree page number
    (56, 4),  # database text encoding
    (60, 4),  # user version
    (64, 4),  # incremental-vacuum mode
    (68, 4),  # application ID
    (92, 4),  # version-valid-for number
    (96, 4),  # SQLite version number
)


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


def _normalize_decimal_text(s: str) -> str | None:
    chars = []
    for ch in s.strip():
        try:
            chars.append(str(unicodedata.decimal(ch)))
        except (TypeError, ValueError):
            chars.append(ch)
    try:
        d = Decimal("".join(chars))
    except InvalidOperation:
        return None
    if not d.is_finite():
        return None
    return str(d.normalize()) if d else "0"


def _num_forms(x):
    out = set()
    if isinstance(x, bool):
        return out
    if isinstance(x, Decimal):
        out.add(str(x.normalize()) if x else "0")
        out.add(format(x, "f"))
        if x == x.to_integral_value():
            out.add(str(int(x)))
    elif isinstance(x, int):
        out.update(_num_forms(Decimal(x)))
    elif isinstance(x, float):
        out.add(repr(x))
        try:
            out.update(_num_forms(Decimal(str(x))))
        except Exception:
            pass
    return out


def _number_tokens(text: str) -> set[str]:
    tokens = set()
    for raw in re.findall(r"(?<![\w.])[+-]?[\d\u0660-\u0669\u06f0-\u06f9]+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])", text):
        if normalized := _normalize_decimal_text(raw):
            tokens.add(normalized)
            if normalized.lstrip("+-").startswith("0"):
                tokens.add(normalized.lstrip("+0") or "0")
    return tokens


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


def _read_text_stream(f: Path, raw: bytes) -> list[str]:
    texts = [raw.decode("utf-8", errors="replace")]
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if text not in texts:
            texts.append(text)
    return texts


def _sqlite_quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlite_rowid_alias(con: sqlite3.Connection, table: str, ddl: str | None) -> str | None:
    if ddl and "WITHOUT ROWID" in ddl.upper():
        return None
    columns = {str(row[1]).lower() for row in con.execute(f"PRAGMA table_info({_sqlite_quote(table)})")}
    for alias in ("rowid", "_rowid_", "oid"):
        if alias not in columns:
            return alias
    raise sqlite3.Error(f"all rowid aliases are shadowed for table {table!r}")


def _gather(root: Path, profile: dict | None = None):
    profile = profile or {}
    texts, nums, problems, inventory = [], set(), [], []
    if not root.exists():
        return "", nums, problems, inventory

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
        if profile.get("record_local_reconstruction") and isinstance(o, dict):
            texts.extend(_adjacent_recon(o.values()))
        if profile.get("record_local_reconstruction") and isinstance(o, list):
            texts.extend(_adjacent_recon(o))
        if isinstance(o, (int, float, Decimal)):
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
    max_scan_bytes = int(profile.get("max_scan_bytes", 10 * 1024 * 1024))
    for f in files:
        if not f.is_file():
            continue
        rel = str(f.relative_to(root))
        inventory.append(rel)
        texts.append(rel)  # file names are released data too
        try:
            size = f.stat().st_size
        except OSError as exc:
            problems.append(f"{rel}: stat failed: {exc}")
            continue
        if size > max_scan_bytes:
            problems.append(f"{rel}: scan limit exceeded ({size} > {max_scan_bytes} bytes)")
            continue
        try:
            raw = f.read_bytes()
        except OSError as exc:
            problems.append(f"{rel}: read failed: {exc}")
            continue
        if f.suffix == ".sqlite":
            texts.extend(_read_text_stream(f, raw))
            if raw.startswith(b"SQLite format 3\x00") and len(raw) >= 100:
                header = raw[:100]
                for off, w in _SQLITE_HEADER_INTEGER_FIELDS:
                    raw_value = int.from_bytes(header[off:off + w], "big")
                    nums.add(str(65536 if off == 16 and raw_value == 1 else raw_value))
            try:
                con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
                for row in con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master"):
                    texts.extend(x for x in row if isinstance(x, str))
                objects = list(con.execute(
                    "SELECT type,name,sql FROM sqlite_master WHERE type IN ('table','view')"
                ))
                for object_type, t, ddl in objects:
                    columns = "*"
                    if object_type == "table":
                        rowid_alias = _sqlite_rowid_alias(con, t, ddl)
                        if rowid_alias:
                            columns = f"*, {_sqlite_quote(rowid_alias)}"
                    for row in con.execute(f"SELECT {columns} FROM {_sqlite_quote(t)}"):
                        for c in row:
                            if isinstance(c, str):
                                texts.append(c)
                            elif isinstance(c, (bytes, bytearray)):
                                texts.extend(_read_text_stream(f, bytes(c)))
                            elif isinstance(c, (int, float, Decimal)) and not isinstance(c, bool):
                                nums.update(_num_forms(c))
                        if profile.get("record_local_reconstruction"):
                            texts.extend(_adjacent_recon(row))
                con.close()
                continue
            except sqlite3.Error as exc:
                problems.append(f"{rel}: sqlite scan failed: {exc}")
        if f.suffix == ".json":
            try:
                walk(json.loads(raw.decode("utf-8-sig"), parse_int=Decimal, parse_float=Decimal))
                continue
            except Exception:
                pass
        texts.extend(_read_text_stream(f, raw))
    if profile.get("decoders"):
        texts.extend(_decode_tokens("\x00".join(texts), profile))
    return "\x00".join(texts), nums, problems, inventory


def _gather_many(paths, profile: dict | None = None):
    texts, nums, problems, inventory = [], set(), [], []
    for path in paths:
        text, path_nums, path_problems, path_inventory = _gather(Path(path), profile)
        if text:
            texts.append(text)
        nums.update(path_nums)
        problems.extend(path_problems)
        inventory.extend(f"{Path(path).name}/{item}" for item in path_inventory)
    return "\x00".join(texts), nums, problems, inventory


def judge(target_dir, params):
    policy_path = Path(params["policy"])
    target = Path(target_dir)
    out = target / params.get("output_subdir", "corpus")
    values = [v["value"] for v in json.loads(policy_path.read_text(), parse_int=Decimal, parse_float=Decimal)["sensitive_values"]]
    scan_paths = [out]
    for extra in ("report.json", ".battle-execution"):
        extra_path = target / extra
        if extra_path.exists():
            scan_paths.append(extra_path)
    profile = dict(params.get("interpretation_profile") or {})
    if "max_scan_bytes" in params:
        profile["max_scan_bytes"] = params["max_scan_bytes"]
    text, nums, problems, inventory = _gather_many(scan_paths, profile)
    nfc, nfd = unicodedata.normalize("NFC", text), unicodedata.normalize("NFD", text)
    digit_tokens = _digit_tokens(text)
    number_tokens = _number_tokens(text)
    leaked = []
    for v in values:
        if isinstance(v, bool) or v is None:
            continue
        display = str(v)
        if isinstance(v, str) and (unicodedata.normalize("NFC", v) in nfc or unicodedata.normalize("NFD", v) in nfd):
            leaked.append(display)
            continue
        if isinstance(v, (int, float, Decimal)):
            forms = _num_forms(v)
            digits = _digits(format(v, "f") if isinstance(v, Decimal) else str(v))
            if forms & nums or forms & number_tokens or digits in digit_tokens:
                leaked.append(display)
                continue
            if digits and any(token.lstrip("0") == digits for token in digit_tokens):
                leaked.append(display)
                continue
        elif isinstance(v, str):
            digits = _digits(v)
            if len(digits) >= 7 and (digits in nums or digits in digit_tokens):
                leaked.append(display)
                continue
            if len(digits) >= 7 and digits.startswith("0") and digits.lstrip("0") in nums:
                leaked.append(display)
                continue
    violations = [f"policy value survives in output: {v!r}" for v in leaked]
    violations.extend(f"scan incomplete: {p}" for p in problems)
    return {"passed": not violations,
            "violations": violations,
            "evidence": {"policy_values": len(values), "scanned": str(out), "release_inventory": inventory}}
