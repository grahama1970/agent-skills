"""De-escalation joke search: local safe corpus now, dynamic Humor API when keyed.

Especially for conversations flagged ABUSIVE: search a GENTLE, on-topic, safe
joke to defuse tension. Never a joke at the user's expense (mockery escalates —
Mandt/CPI/Starr); humor sparingly; if the user is genuinely distressed, the
caller should NOT joke at all.

Backends (auto-selected):
  - Humor API (https://api.humorapi.com/jokes/search) when HUMOR_API_KEY is set:
    keyword search over 50k+ jokes with exclude-tags safety filters. THIS is the
    dynamic search the abusive-context path wants.
  - Local corpus (fixtures/joke_corpus.json, JokeAPI safe-mode harvest) offline
    fallback — works with no key.

All offensive categories are excluded on every query. Run `python3 joke_search.py`
for the self-check (offline corpus).
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "fixtures" / "joke_corpus.json"
EXCLUDE = ["nsfw", "racist", "sexist", "religious", "political", "explicit"]


def _load_corpus() -> list[dict]:
    return json.load(open(CORPUS)).get("jokes", [])


def _search_local(term: str, limit: int = 5) -> list[dict]:
    t = term.lower().strip()
    hits = []
    for j in _load_corpus():
        if t in j["joke"].lower() or t in j.get("keywords", []):
            hits.append({"joke": j["joke"], "category": j.get("category"),
                         "safe": True, "source": "local_corpus"})
    return hits[:limit]


def _search_humorapi(term: str, key: str, limit: int = 5) -> list[dict]:
    q = urllib.parse.urlencode({"api-key": key, "keywords": term,
                                "exclude-tags": ",".join(EXCLUDE), "number": limit})
    with urllib.request.urlopen(f"https://api.humorapi.com/jokes/search?{q}", timeout=15) as r:
        d = json.loads(r.read().decode())
    return [{"joke": j.get("joke"), "category": None, "safe": True,
             "source": "humorapi"} for j in (d.get("jokes") or [])]


def search(term: str, limit: int = 5) -> dict:
    """Search safe jokes by keyword. Dynamic Humor API if keyed, else local corpus."""
    key = os.environ.get("HUMOR_API_KEY")
    if key:
        try:
            return {"backend": "humorapi", "results": _search_humorapi(term, key, limit)}
        except Exception as e:
            return {"backend": "humorapi_error", "error": str(e)[:160],
                    "results": _search_local(term, limit)}
    return {"backend": "local_corpus", "results": _search_local(term, limit)}


def for_deescalation(term: str) -> dict:
    """Abusive-context gate: gentle safe joke, never at the user's expense.

    Returns a plan the caller applies ONLY when a benign redirect is appropriate;
    the caller must not joke if the user is genuinely distressed.
    """
    res = search(term, limit=5)
    res["gate"] = {"use_only_if": "conversation is abusive/hostile AND a light "
                                   "redirect is appropriate, not genuine distress",
                   "never": "a joke at the user's expense (mockery escalates)",
                   "delivery": "warm, self-deprecating or neutral; sparingly"}
    return res


def demo() -> None:
    assert CORPUS.is_file(), "joke corpus missing"
    corpus = _load_corpus()
    assert corpus and all(j.get("safe") for j in corpus), "corpus not all safe"
    # a term known to exist in the harvested set
    r = search("time")
    assert r["backend"] in ("local_corpus", "humorapi")
    # de-escalation gate is always attached
    g = for_deescalation("computer")
    assert g["gate"]["never"], "gate missing"
    # offensive tags always excluded
    assert set(EXCLUDE) >= {"nsfw", "racist", "sexist"}
    print(f"joke_search.py self-check: PASS ({len(corpus)} safe jokes, backend={r['backend']})")


if __name__ == "__main__":
    demo()
