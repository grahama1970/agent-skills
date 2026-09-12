"""Reference functional judge: the anonymizer's useful-transformation invariant.

WebGPT step 3 (accept-and-destroy loophole): a target that accepts MUST_ACCEPT
cases while emitting garbage must FAIL. This judge compares the released output
corpus against the INPUT corpus modulo independently bound replacement slots:

- complete inventory: every input file has exactly one output file (and no extras)
- unchanged content: every literal outside a policy-value occurrence is preserved
- replacement validity: every slot is a non-empty replacement, never the value
- identity coherence: one value -> one stable replacement within the run;
  distinct same-type values never share a replacement

It is a comparator for declared fixture structures, NOT a second anonymizer:
no pseudonym generation, no SQL rewriting, no search for plausible
correspondence. Unsupported structures fail with functional-oracle-unsupported.

params: {"policy": <path>, "output_subdir": "corpus", "input_dir": <case input dir>}
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import unicodedata
from pathlib import Path


def _num_forms(text: str):
    forms = {text}
    try:
        i = int(text)
        forms.add(i)
        forms.add(float(i))
    except ValueError:
        try:
            f = float(text)
            forms.add(f)
            if f.is_integer():
                forms.add(int(f))
        except ValueError:
            pass
    return forms


def _is_slot(scalar, value: str) -> bool:
    if isinstance(scalar, bool) or scalar is None:
        return False
    if isinstance(scalar, str):
        return unicodedata.normalize("NFC", scalar) == unicodedata.normalize("NFC", value)
    return scalar in _num_forms(value)


class _Comparator:
    def __init__(self, values: list[str], types: list[str], subjects: list[str]):
        self.values = sorted(values, key=len, reverse=True)
        self.types = types
        self.subjects = subjects  # identity group per value (subject_id); aliases may converge
        self.bindings: dict[str, str] = {}
        self.violations: list[str] = []

    def bind(self, value: str, replacement, where: str) -> None:
        if not isinstance(replacement, str) or not replacement.strip():
            self.violations.append(f"functional:{where}: empty, blank, or non-string replacement for a policy occurrence")
            return
        if value in replacement:
            self.violations.append(f"functional:{where}: replacement still contains the policy value")
            return
        existing = self.bindings.get(value)
        if existing is not None and existing != replacement:
            self.violations.append(f"functional:{where}: inconsistent replacement for same value ({existing!r} vs {replacement!r})")
            return
        self.bindings[value] = replacement

    def check_coherence(self) -> None:
        # Identity-group rule (brief: aliases of one identity may intentionally
        # converge; distinct identity groups must not share a replacement).
        by_rep: dict[str, tuple[str, str]] = {}  # replacement -> (value, subject)
        for value, rep in self.bindings.items():
            idx = self.values.index(value)
            raw_subject = self.subjects[idx] if idx < len(self.subjects) else ""
            # Rules sharing a subject group may converge; rules with no identity
            # info are distinct groups (fail-closed, per the brief).
            subject = raw_subject or f"\x00distinct-{idx}"
            other = by_rep.get(rep)
            if other is not None and other[1] != subject:
                self.violations.append(f"functional:collapsed-identities: {other[0]!r} (subject {other[1]!r}) and {value!r} (subject {subject!r}) share replacement {rep!r}")
            by_rep[rep] = (value, subject)

    # -- text skeleton: literals preserved in order, gaps bound as slots.
    # Comparison is NFC-folded: the trial brief permits normalization, so a
    # literal preserved up to Unicode normalization is preserved.
    def text(self, in_text: str, out_text: str, where: str) -> None:
        in_text = unicodedata.normalize("NFC", in_text)
        out_text = unicodedata.normalize("NFC", out_text)
        # Tokenize input into alternating segments: literal runs and value hits.
        tokens: list[tuple[str, str | None]] = []  # (kind, text) kind in {"lit", "val"}
        pos = 0
        while pos < len(in_text):
            hit = next((v for v in self.values if in_text.startswith(v, pos)), None)
            if hit is None:
                if tokens and tokens[-1][0] == "lit":
                    tokens[-1] = ("lit", tokens[-1][1] + in_text[pos])
                else:
                    tokens.append(("lit", in_text[pos]))
                pos += 1
            else:
                tokens.append(("val", hit))
                pos += len(hit)
        cursor = 0
        i = 0
        while i < len(tokens):
            kind, text = tokens[i]
            if kind == "lit":
                if not out_text.startswith(text, cursor):
                    self.violations.append(f"functional:{where}: literal segment missing/modified in output near offset {cursor} ({text[:24]!r})")
                    return
                cursor += len(text)
                i += 1
            else:
                # find the next literal token (may be none) to bound the replacement
                next_lit = None
                for j in range(i + 1, len(tokens)):
                    if tokens[j][0] == "lit" and tokens[j][1]:
                        next_lit = tokens[j][1]
                        break
                if next_lit is None:
                    replacement = out_text[cursor:]
                    cursor = len(out_text)
                    i += 1
                else:
                    idx = out_text.find(next_lit, cursor)
                    if idx < 0:
                        self.violations.append(f"functional:{where}: literal segment missing/modified in output")
                        return
                    replacement = out_text[cursor:idx]
                    cursor = idx
                    i += 1
                self.bind(text, replacement, where)
        if cursor != len(out_text):
            self.violations.append(f"functional:{where}: output has trailing extra content after last expected segment")

    # -- csv: parsed rows; whole-cell slots only --
    def csv_rows(self, in_rows: list[list[str]], out_rows: list[list[str]], where: str) -> None:
        if len(in_rows) != len(out_rows):
            self.violations.append(f"functional:{where}: row count changed ({len(in_rows)} -> {len(out_rows)})")
            return
        for r, (rin, rout) in enumerate(zip(in_rows, out_rows)):
            if len(rin) != len(rout):
                self.violations.append(f"functional:{where}: row {r} width changed")
                return
            for c, (a, b) in enumerate(zip(rin, rout)):
                if a in self.values:
                    self.bind(a, b, f"{where}:row{r}:cell{c}")
                elif unicodedata.normalize("NFC", a) != unicodedata.normalize("NFC", b):
                    self.violations.append(f"functional:{where}:row{r}:cell{c}: non-slot cell changed ({a!r} -> {b!r})")

    # -- json: structural walk with slot scalars --
    def json_walk(self, a, b, where: str) -> None:
        if isinstance(a, dict):
            if not isinstance(b, dict) or set(a.keys()) != set(b.keys()):
                self.violations.append(f"functional:{where}: object keys changed")
                return
            for k in a:
                self.json_walk(a[k], b[k], f"{where}.{k}")
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                self.violations.append(f"functional:{where}: array length/order changed")
                return
            for i, (x, y) in enumerate(zip(a, b)):
                self.json_walk(x, y, f"{where}[{i}]")
        elif any(_is_slot(a, v) for v in self.values):
            hit = next(v for v in self.values if _is_slot(a, v))
            self.bind(hit, b, where)
        else:
            if isinstance(a, str) and isinstance(b, str):
                if unicodedata.normalize("NFC", a) != unicodedata.normalize("NFC", b):
                    self.violations.append(f"functional:{where}: scalar changed ({a!r} -> {b!r})")
            elif isinstance(a, bool) or isinstance(b, bool):
                if a is not b:
                    self.violations.append(f"functional:{where}: scalar changed ({a!r} -> {b!r})")
            elif a != b:
                self.violations.append(f"functional:{where}: scalar changed ({a!r} -> {b!r})")

    # -- sqlite: schema tuples + typed row multisets + integrity --
    def sqlite(self, in_db: Path, out_db: Path, where: str) -> None:
        def schema(con):
            rows = con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master").fetchall()
            return sorted(tuple(r) for r in rows if not str(r[1]).startswith("sqlite_"))
        def tables(con):
            return [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'")]
        cin = sqlite3.connect(f"file:{in_db}?mode=ro", uri=True)
        cout = sqlite3.connect(f"file:{out_db}?mode=ro", uri=True)
        sin, sout = schema(cin), schema(cout)
        if sin != sout:
            self.violations.append(f"functional:{where}: schema objects changed")
        for t in tables(cin):
            try:
                rows_in = cin.execute(f'SELECT * FROM "{t}"').fetchall()
                rows_out = cout.execute(f'SELECT * FROM "{t}"').fetchall()
            except sqlite3.Error as exc:
                self.violations.append(f"functional:{where}: table {t} unreadable ({exc})")
                continue
            if len(rows_in) != len(rows_out):
                self.violations.append(f"functional:{where}: table {t} row count changed")
                continue
            used = [False] * len(rows_out)
            for rin in rows_in:
                matched = False
                for j, rout in enumerate(rows_out):
                    if used[j]:
                        continue
                    ok = True
                    for a, b in zip(rin, rout):
                        if any(_is_slot(a, v) for v in self.values):
                            hit = next(v for v in self.values if _is_slot(a, v))
                            if not isinstance(b, str) or not b or hit in b:
                                ok = False
                                break
                            self.bind(hit, b, f"{where}:{t}")
                        elif isinstance(a, bool) or isinstance(b, bool):
                            ok = a is b
                        elif a != b:
                            ok = False
                        if not ok:
                            break
                    if ok:
                        used[j] = True
                        matched = True
                        break
                if not matched:
                    self.violations.append(f"functional:{where}: table {t}: input row has no matching output row")
        if cout.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            self.violations.append(f"functional:{where}: integrity_check failed")
        if cout.execute("PRAGMA foreign_key_check").fetchall():
            self.violations.append(f"functional:{where}: foreign_key_check failed")
        cin.close()
        cout.close()


def _read_text(p: Path) -> str:
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8")


def judge(target_dir, params):
    inp = Path(params["input_dir"]) / "corpus"
    out = Path(target_dir) / params.get("output_subdir", "corpus")
    policy = json.loads(Path(params["policy"]).read_text(encoding="utf-8"))
    entries = policy.get("sensitive_values", [])
    values = [str(e["value"]) for e in entries]
    types = [str(e.get("type", "")) for e in entries]
    subjects = [str(e.get("subject_id", e.get("rule_id", ""))) for e in entries]
    cmp_ = _Comparator(values, types, subjects)

    in_files = sorted(str(p.relative_to(inp)) for p in inp.rglob("*") if p.is_file())
    out_files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    if in_files != out_files:
        missing = [f for f in in_files if f not in out_files]
        extra = [f for f in out_files if f not in in_files]
        cmp_.violations.append(f"functional:inventory-mismatch: missing={missing} extra={extra}")
    for rel in in_files:
        if rel not in out_files:
            continue
        a, b = inp / rel, out / rel
        suffix = a.suffix
        try:
            if suffix == ".json":
                cmp_.json_walk(json.loads(_read_text(a)), json.loads(_read_text(b)), rel)
            elif suffix == ".csv":
                cmp_.csv_rows(list(csv.reader(io.StringIO(_read_text(a)))),
                              list(csv.reader(io.StringIO(_read_text(b)))), rel)
            elif suffix == ".txt":
                cmp_.text(_read_text(a), _read_text(b), rel)
            elif suffix == ".sqlite":
                cmp_.sqlite(a, b, rel)
            else:
                cmp_.violations.append(f"functional:{rel}: functional-oracle-unsupported (suffix {suffix})")
        except Exception as exc:  # fail-closed: unreadable structure is a failure
            cmp_.violations.append(f"functional:{rel}: unreadable structure ({type(exc).__name__}: {exc})")
    cmp_.check_coherence()
    # Minimal report contract: a successful release must ship a parseable
    # report.json whose status is compatible with the observed run.
    report = Path(target_dir) / "report.json"
    if not report.is_file():
        cmp_.violations.append("functional:report-missing: successful release has no report.json")
    else:
        try:
            rp = json.loads(report.read_text(encoding="utf-8"))
            status = str(rp.get("status", ""))
            if status not in ("ready", "pass", "PASS", "ok"):
                cmp_.violations.append(f"functional:report-status-incompatible: {status!r}")
        except Exception as exc:
            cmp_.violations.append(f"functional:report-malformed: {type(exc).__name__}: {exc}")
    return {"passed": not cmp_.violations,
            "violations": cmp_.violations,
            "evidence": {"files_compared": len(in_files),
                         "values": len(values),
                         "bindings": {k: v for k, v in cmp_.bindings.items()}}}
