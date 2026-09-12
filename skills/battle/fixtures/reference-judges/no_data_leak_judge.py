"""Reference invariant judge: no policy sensitive value leaks into the output.

This is the anonymizer confidentiality invariant expressed as a Battle Judge.
params: {"policy": "<path to policy.json>", "output_subdir": "corpus"}.
It independently scans the released output (JSON scalars incl decoded \\u,
numeric expansion, SQLite cells + schema DDL + header integers, text/CSV,
report.json) for any policy value in any representation.

Because Battle judges are independent and deterministic, this same judge can be
reused by Red (adversarially search for an input that makes it FAIL) and by the
scorekeeper (score the Judge result, not an agent claim).
"""
from __future__ import annotations

import json
import sqlite3
import unicodedata
from decimal import Decimal
from pathlib import Path


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


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


def _gather(root: Path):
    texts, nums = [], set()

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
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

    for f in sorted(root.rglob("*")):
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
            con.close()
            header = f.read_bytes()[:100]
            for off, w in ((16, 2), (28, 4), (40, 4), (48, 4), (52, 4), (56, 4), (60, 4), (64, 4), (68, 4)):
                nums.add(str(int.from_bytes(header[off:off + w], "big")))
    return "\x00".join(texts), nums


def judge(target_dir, params):
    policy_path = Path(params["policy"])
    out = Path(target_dir) / params.get("output_subdir", "corpus")
    values = [str(v["value"]) for v in json.loads(policy_path.read_text())["sensitive_values"]]
    text, nums = _gather(out)
    nfc, nfd = unicodedata.normalize("NFC", text), unicodedata.normalize("NFD", text)
    leaked = []
    for v in values:
        if unicodedata.normalize("NFC", v) in nfc or unicodedata.normalize("NFD", v) in nfd:
            leaked.append(v)
            continue
        digits = _digits(v)
        if len(digits) >= 7 and digits in nums:
            leaked.append(v)
            continue
        if len(digits) >= 7 and digits.startswith("0") and digits.lstrip("0") in nums:
            leaked.append(v)
            continue
    return {"passed": not leaked,
            "violations": [f"policy value survives in output: {v!r}" for v in leaked],
            "evidence": {"policy_values": len(values), "scanned": str(out)}}
