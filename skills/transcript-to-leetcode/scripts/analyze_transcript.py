#!/usr/bin/env python3
"""Deterministically reconstruct a coding problem from interview transcript data.

The script never solves the problem. It emits a fail-closed contract that either
asks blocking clarifying questions or authorizes a later code-generation step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = "transcript_to_leetcode.analysis.v1"
MAX_INPUT_CHARS = 250_000
MAX_SELECTED_CHARS = 6_000
MAX_CANDIDATES = 3
MAX_QUESTIONS = 3

INTERVIEWER = {"interviewer", "recruiter", "hiring manager", "manager", "questioner"}
CANDIDATE = {"candidate", "interviewee", "graham", "applicant"}
INTERIM = {"interim", "partial", "unstable"}
STABLE = {"final", "stabilized", "stable", "complete"}
ACTIONS = {"build", "calculate", "count", "design", "determine", "find", "implement", "return", "remove", "reverse", "solve", "write"}
DATA_TERMS = ("array", "binary tree", "characters", "graph", "grid", "interval", "linked list", "list", "matrix", "node", "numbers", "parentheses", "string", "tree")
SMALLTALK = ("how are you", "ready to get started", "tell me about yourself", "walk me through your resume")

SPEAKER_RE = re.compile(
    r"^\s*(?:\[[^\]]{1,40}\]\s*)?(?P<speaker>interviewer|interviewee|candidate|recruiter|hiring manager|manager|graham|applicant|questioner|unknown)\s*(?::|[-–—]>?)\s*(?P<text>.*)$",
    re.IGNORECASE,
)
TIMESTAMP_RE = re.compile(r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?\s*-->\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?\s*$")


@dataclass(frozen=True, slots=True)
class Turn:
    speaker: str
    text: str
    line_start: int
    line_end: int
    event_id: str | None = None
    sequence: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True, slots=True)
class Archetype:
    slug: str
    title: str
    family: str
    patterns: tuple[str, ...]
    keywords: tuple[str, ...]


ARCHETYPES = (
    Archetype("minimum-remove-valid-parentheses", "Minimum Remove to Make Valid Parentheses", "stack / two-pass string cleanup", (r"minimum(?: number of)? (?:parentheses|parenthesis).{0,60}(?:remove|removal)", r"remove.{0,60}minimum.{0,60}(?:valid|balanced).{0,50}(?:parentheses|parenthesis)", r"remove.{0,60}minimum.{0,60}(?:parentheses|parenthesis).{0,50}(?:valid|balanced)", r"make.{0,50}(?:parentheses|parenthesis).{0,30}valid"), ("minimum", "remove", "valid", "parentheses", "string")),
    Archetype("valid-parentheses", "Valid Parentheses", "stack", (r"(?:valid|balanced).{0,40}(?:parentheses|parenthesis|brackets)", r"opening.{0,30}closing.{0,30}(?:parentheses|parenthesis|brackets)"), ("valid", "balanced", "opening", "closing", "parentheses", "brackets", "stack")),
    Archetype("two-sum", "Two Sum", "hash map", (r"two (?:numbers|integers|elements).{0,55}(?:add|sum).{0,25}target", r"target.{0,50}(?:pair|two).{0,35}(?:indices|indexes|numbers)", r"find.{0,40}(?:pair|two elements).{0,40}sum"), ("two", "pair", "sum", "target", "indices", "array", "numbers")),
    Archetype("longest-substring-no-repeat", "Longest Substring Without Repeating Characters", "sliding window", (r"longest substring.{0,45}(?:without|no).{0,25}(?:repeat|repeating|duplicate)", r"substring.{0,45}unique characters"), ("longest", "substring", "repeating", "unique", "characters", "string")),
    Archetype("merge-intervals", "Merge Intervals", "sorting / interval sweep", (r"merge.{0,35}(?:overlapping )?intervals", r"intervals.{0,40}overlap.{0,30}merge"), ("merge", "intervals", "overlap", "start", "end")),
    Archetype("binary-search", "Binary Search", "binary search", (r"sorted (?:array|list).{0,60}(?:find|search).{0,25}target", r"binary search"), ("sorted", "array", "target", "index", "binary", "search")),
    Archetype("number-of-islands", "Number of Islands", "graph traversal / flood fill", (r"(?:count|number of).{0,30}islands.{0,35}(?:grid|matrix)", r"grid.{0,45}(?:land|water).{0,45}islands"), ("grid", "matrix", "islands", "land", "water", "adjacent", "count")),
    Archetype("reverse-linked-list", "Reverse Linked List", "linked-list pointer manipulation", (r"reverse.{0,30}linked list", r"linked list.{0,30}reverse"), ("reverse", "linked", "list", "node", "next", "head")),
    Archetype("top-k-frequent", "Top K Frequent Elements", "frequency map / heap or bucket sort", (r"top k.{0,35}(?:frequent|frequency).{0,30}(?:elements|numbers|words)", r"k most frequent"), ("top", "k", "frequent", "frequency", "elements", "numbers", "words")),
    Archetype("course-schedule", "Course Schedule", "topological sort / cycle detection", (r"course.{0,35}prerequisite.{0,45}(?:finish|complete|possible)", r"prerequisite.{0,45}(?:cycle|ordering|schedule)"), ("course", "courses", "prerequisite", "finish", "cycle", "directed")),
    Archetype("meeting-rooms-ii", "Meeting Rooms II", "interval sweep / min-heap", (r"minimum.{0,30}(?:meeting|conference) rooms", r"meetings.{0,45}(?:rooms|overlap).{0,25}minimum"), ("meeting", "meetings", "rooms", "intervals", "overlap", "minimum")),
    Archetype("lru-cache", "LRU Cache", "hash map / doubly linked list", (r"lru cache", r"least recently used.{0,25}cache"), ("lru", "cache", "least", "recently", "used", "get", "put", "capacity")),
    Archetype("kth-largest", "Kth Largest Element in an Array", "heap / quickselect", (r"k(?:th| th).{0,25}largest.{0,30}(?:array|element|number)", r"find.{0,30}k.{0,20}largest"), ("kth", "largest", "array", "element", "k")),
    Archetype("product-except-self", "Product of Array Except Self", "prefix / suffix products", (r"product.{0,40}(?:array|elements).{0,35}except (?:itself|self)", r"without division.{0,45}product"), ("product", "array", "except", "self", "without", "division")),
    Archetype("maximum-subarray", "Maximum Subarray", "dynamic programming / Kadane's algorithm", (r"maximum.{0,30}(?:sum )?subarray", r"contiguous.{0,30}subarray.{0,30}largest sum"), ("maximum", "largest", "sum", "subarray", "contiguous", "array")),
)


class InputError(ValueError):
    pass


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def speaker(value: Any) -> str:
    name = clean(value).casefold()
    if name in INTERVIEWER:
        return "interviewer"
    if name in CANDIDATE:
        return "candidate"
    return "unknown"


def nonnegative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def turn_from_object(obj: dict[str, Any], line: int) -> Turn | None:
    payload = obj.get("payload")
    if isinstance(payload, dict):
        if clean(obj.get("kind")).casefold() not in {"", "transcript"}:
            return None
        obj = payload
    schema = clean(obj.get("schema") or obj.get("schema_id"))
    if schema == "live_evidence.question_candidate.v1" or "normalized_question" in obj:
        text = clean(obj.get("normalized_question"))
        return Turn("interviewer", text, line, line, clean(obj.get("question_id")) or None, nonnegative_int(obj.get("start_sequence"))) if text else None
    text = clean(obj.get("text") or obj.get("transcript") or obj.get("utterance"))
    if not text:
        return None
    kind = clean(obj.get("kind") or obj.get("stability")).casefold()
    if obj.get("final") is False or kind in INTERIM:
        return None
    if schema == "live_evidence.transcript_event.v1" and kind and kind not in STABLE:
        return None
    return Turn(speaker(obj.get("speaker") or obj.get("role")), text, line, line, clean(obj.get("event_id") or obj.get("id")) or None, nonnegative_int(obj.get("sequence")), nonnegative_int(obj.get("start_ms")), nonnegative_int(obj.get("end_ms")))


def turns_from_json(value: Any) -> list[Turn]:
    if isinstance(value, list):
        return [turn for i, item in enumerate(value, 1) if isinstance(item, dict) and (turn := turn_from_object(item, i))]
    if isinstance(value, dict):
        for key in ("events", "turns", "transcript", "items"):
            if isinstance(value.get(key), list):
                return turns_from_json(value[key])
        turn = turn_from_object(value, 1)
        return [turn] if turn else []
    return []


def parse_text(raw: str) -> list[Turn]:
    turns: list[Turn] = []
    active_speaker = "unknown"
    active: list[str] = []
    start = 1

    def flush(end: int) -> None:
        nonlocal active
        text = clean(" ".join(active))
        if text:
            turns.append(Turn(active_speaker, text, start, max(start, end)))
        active = []

    lines = raw.splitlines()
    for number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.upper() == "WEBVTT" or line.isdigit() or TIMESTAMP_RE.match(line):
            continue
        match = SPEAKER_RE.match(line)
        if match:
            flush(number - 1)
            active_speaker = speaker(match.group("speaker"))
            start = number
            if text := clean(match.group("text")):
                active.append(text)
        else:
            if not active:
                start = number
            active.append(line)
    flush(len(lines) or 1)
    return turns


def parse_transcript(raw: str) -> tuple[list[Turn], str]:
    if not raw.strip():
        raise InputError("transcript is empty")
    if len(raw) > MAX_INPUT_CHARS:
        raise InputError(f"transcript exceeds {MAX_INPUT_CHARS} characters")
    stripped = raw.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            return turns_from_json(json.loads(raw)), "json"
        except json.JSONDecodeError:
            pass
    rows = [(i, line) for i, line in enumerate(raw.splitlines(), 1) if line.strip()]
    parsed: list[Turn] = []
    json_rows = 0
    for number, line in rows:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        json_rows += 1
        if isinstance(value, dict) and (turn := turn_from_object(value, number)):
            parsed.append(turn)
    if rows and json_rows == len(rows):
        return parsed, "jsonl"
    return parse_text(raw), "text"


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#]+", text.casefold()))


def contains_any(text: str, phrases: Iterable[str]) -> int:
    lower = text.casefold()
    return sum(phrase in lower for phrase in phrases)


def coding_score(text: str) -> float:
    lower = text.casefold()
    score = min(len(words(text) & ACTIONS), 4) * 1.3
    score += min(contains_any(lower, DATA_TERMS), 4) * 1.2
    score += 0.6 if "?" in text else 0.0
    score += 1.0 if any(token in lower for token in ("given ", "write a function", "implement ")) else 0.0
    score -= 3.0 * contains_any(lower, SMALLTALK)
    return score


def problem_windows(turns: Sequence[Turn]) -> list[list[Turn]]:
    windows: list[list[Turn]] = []
    current: list[Turn] = []
    for turn in turns:
        if turn.speaker == "candidate":
            if current:
                windows.append(current)
                current = []
            continue
        if turn.speaker in {"interviewer", "unknown"}:
            current.append(turn)
    if current:
        windows.append(current)
    return windows


def select_window(turns: Sequence[Turn]) -> tuple[list[Turn], float]:
    ranked = [(coding_score(" ".join(t.text for t in window)), index, window) for index, window in enumerate(problem_windows(turns))]
    if not ranked:
        return [], 0.0
    score, _, window = max(ranked, key=lambda item: (item[0], item[1]))
    text = clean(" ".join(turn.text for turn in window))
    while len(text) > MAX_SELECTED_CHARS and len(window) > 1:
        window = window[1:]
        text = clean(" ".join(turn.text for turn in window))
    return window, score


def evidence(text: str, terms: Sequence[str]) -> list[str]:
    lower = text.casefold()
    return [term for term in terms if term in lower][:5]


def rank_archetypes(text: str) -> list[dict[str, Any]]:
    lower = text.casefold()
    ranked: list[tuple[float, dict[str, Any]]] = []
    for archetype in ARCHETYPES:
        pattern_hits = sum(bool(re.search(pattern, lower)) for pattern in archetype.patterns)
        keyword_hits = evidence(lower, archetype.keywords)
        coverage = len(keyword_hits) / max(len(archetype.keywords), 1)
        score = pattern_hits * 0.58 + coverage * 0.42
        if pattern_hits == 0 and coverage < 0.34:
            continue
        confidence = round(min(0.99, 0.34 + score * 0.49), 3)
        match_kind = "likely_exact" if pattern_hits and coverage >= 0.42 and confidence >= 0.62 else "archetype_only"
        ranked.append((confidence, {"slug": archetype.slug, "title": archetype.title, "family": archetype.family, "confidence": confidence, "match_kind": match_kind, "evidence": keyword_hits}))
    ranked.sort(key=lambda item: (-item[0], item[1]["title"]))
    return [item for _, item in ranked[:MAX_CANDIDATES]]


def sentence(text: str, pattern: str) -> str | None:
    for part in re.split(r"(?<=[.!?])\s+", text):
        if re.search(pattern, part, re.IGNORECASE):
            return clean(part)[:800]
    return None


def extract_facts(text: str, answers: dict[str, str]) -> dict[str, Any]:
    lower = text.casefold()
    return_contract = None
    for pattern, value in ((r"return.{0,35}(?:two )?(?:indices|indexes)", "indices"), (r"return.{0,25}(?:the )?(?:values|numbers|elements)", "values"), (r"return.{0,30}(?:any )?valid string", "string"), (r"return.{0,25}(?:the )?(?:count|number)", "count"), (r"return.{0,25}(?:true|false|boolean|bool)", "boolean"), (r"return.{0,25}(?:new )?head", "head"), (r"return.{0,25}(?:merged )?list", "list"), (r"return.{0,25}(?:index|position)", "index")):
        if re.search(pattern, lower):
            return_contract = value
            break
    language = next((name for token, name in (("python", "Python 3"), ("typescript", "TypeScript"), ("javascript", "JavaScript"), ("java", "Java"), ("c++", "C++"), ("golang", "Go"), ("rust", "Rust")) if token in lower), None)
    return {
        "goal": sentence(text, r"\b(?:given|write|implement|find|return|remove|merge|reverse|count|design)\b"),
        "input_description": sentence(text, r"\b(?:given|input|array|string|grid|interval|linked list|graph)\b"),
        "output_description": sentence(text, r"\b(?:return|output)\b"),
        "return_contract": return_contract,
        "distinct_elements": "distinct" if re.search(r"distinct indices|not (?:use|reuse) the same element|may not use the same element", lower) else None,
        "multiple_solutions": "one" if re.search(r"exactly one solution|one solution exists", lower) else ("any" if re.search(r"return any (?:solution|pair|valid string)", lower) else None),
        "non_bracket_policy": "preserve" if re.search(r"letters? and (?:parentheses|brackets)|contains .{0,30}(?:letters|characters).{0,20}(?:parentheses|brackets)", lower) else None,
        "valid_output_choice": "any" if re.search(r"return any valid", lower) else None,
        "substring_output": "length" if re.search(r"return (?:the )?length", lower) else ("substring" if re.search(r"return (?:the )?substring", lower) else None),
        "touching_intervals": "merge" if re.search(r"touching intervals?.{0,20}(?:overlap|merge)", lower) else ("separate" if re.search(r"touching intervals?.{0,20}(?:separate|do not overlap)", lower) else None),
        "grid_adjacency": "4-directional" if re.search(r"four[- ]direction|horizontal(?:ly)? and vertical(?:ly)?", lower) else ("8-directional" if re.search(r"eight[- ]direction|diagonal", lower) else None),
        "grid_mutation": "allowed" if re.search(r"may mutate|can modify", lower) else ("forbidden" if re.search(r"do not mutate|cannot modify", lower) else None),
        "list_mutation": "in-place" if re.search(r"in[- ]place|existing nodes", lower) else None,
        "course_output": "ordering" if re.search(r"return.{0,20}(?:ordering|order)", lower) else ("boolean" if re.search(r"return.{0,20}(?:true|false|boolean)", lower) else None),
        "constraints": sentence(text, r"\b(?:up to|complexity|linear time|log n|constant space|o\()"),
        "language_detected": language,
        "clarification_answers": dict(sorted(answers.items())),
    }


def question(question_id: str, text: str, why: str) -> dict[str, str]:
    return {"id": question_id, "question": text, "why_blocking": why}


def blocking_questions(primary: str | None, facts: dict[str, Any], answers: dict[str, str], candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []

    def ask(question_id: str, text: str, why: str) -> None:
        if question_id not in answers and len(result) < MAX_QUESTIONS:
            result.append(question(question_id, text, why))

    if primary == "two-sum":
        if not facts["return_contract"]:
            ask("return-contract", "Should the function return the two indices, the two values, or a boolean?", "Those contracts require different signatures and outputs.")
        if not facts["distinct_elements"]:
            ask("element-reuse", "Must the two entries be distinct, or may one element be reused?", "The duplicate and self-pair cases depend on this rule.")
        if not facts["multiple_solutions"]:
            ask("multiple-solutions", "Is exactly one solution guaranteed; otherwise, which valid pair should be returned?", "The no-solution and tie behavior must be explicit.")
    elif primary == "minimum-remove-valid-parentheses":
        if not facts["non_bracket_policy"]:
            ask("non-bracket-characters", "May the string contain non-parenthesis characters, and must they be preserved?", "Filtering those characters would change the required output.")
        if not facts["valid_output_choice"]:
            ask("valid-output-choice", "When several minimum-removal strings are valid, may the function return any one?", "Tie behavior affects the output contract.")
    elif primary == "valid-parentheses" and not facts["non_bracket_policy"]:
        ask("non-bracket-characters", "Does the input contain only bracket characters, or should other characters be ignored or rejected?", "Each policy changes validation behavior.")
    elif primary == "longest-substring-no-repeat" and not facts["substring_output"]:
        ask("substring-output", "Should the function return the maximum length, the substring itself, or both?", "Those are different public contracts.")
    elif primary == "merge-intervals" and not facts["touching_intervals"]:
        ask("touching-intervals", "Should endpoint-touching intervals such as [1,4] and [4,5] be merged?", "Endpoint semantics determine whether those intervals overlap.")
    elif primary == "number-of-islands":
        if not facts["grid_adjacency"]:
            ask("grid-adjacency", "Are cells connected in four directions only, or do diagonals count?", "Connectivity changes the island count.")
        if not facts["grid_mutation"]:
            ask("grid-mutation", "May the solution mutate the grid to mark visited cells?", "Mutation policy changes the space tradeoff.")
    elif primary == "reverse-linked-list" and not facts["list_mutation"]:
        ask("list-mutation", "Must the existing nodes be reversed in place, or may new nodes be allocated?", "The two contracts have different space guarantees.")
    elif primary == "course-schedule" and not facts["course_output"]:
        ask("course-output", "Should the function return only whether completion is possible, or a valid course ordering?", "Cycle detection and ordering have different outputs.")
    elif primary == "lru-cache":
        ask("cache-api", "What are the required method names, miss return value, and capacity bounds?", "An LRU implementation must match the exact test API.")

    if len(candidates) > 1 and len(result) < MAX_QUESTIONS:
        first, second = candidates[:2]
        if first["match_kind"] != "likely_exact" or first["confidence"] - second["confidence"] < 0.12:
            ask("problem-selection", "Which reconstructed problem is intended, or what transcript detail distinguishes the top candidates?", "Solving the wrong candidate would be confidently incorrect.")
    exact = bool(candidates) and candidates[0]["match_kind"] == "likely_exact"
    if not facts["constraints"] and not exact and len(result) < MAX_QUESTIONS:
        ask("scale-complexity", "What input-size bounds or target time/space complexity should the solution meet?", "Scale can rule out otherwise-correct brute-force approaches.")
    return result[:MAX_QUESTIONS]


def source_refs(window: Sequence[Turn]) -> list[dict[str, Any]]:
    return [{"speaker": turn.speaker, "line_start": turn.line_start, "line_end": turn.line_end, "event_id": turn.event_id, "sequence": turn.sequence, "start_ms": turn.start_ms, "end_ms": turn.end_ms, "text": turn.text[:1_000]} for turn in window]


def solver_prompt(problem: str, candidates: list[dict[str, Any]], facts: dict[str, Any], language: str) -> str:
    primary = candidates[0] if candidates else None
    label = f"Likely archetype: {primary['title']} ({primary['match_kind']}, confidence {primary['confidence']})." if primary else "No exact title is established."
    return clean(f"Solve this interview coding problem in {language}. {label} Problem: {problem} Clarifications: {json.dumps(facts['clarification_answers'], sort_keys=True)}. State the invariant or correctness argument, give time and space complexity, provide complete code, and include focused tests. Do not rely on unstated LeetCode defaults.")


def analyze(raw: str, answers: dict[str, str], default_language: str) -> dict[str, Any]:
    turns, input_format = parse_transcript(raw)
    window, score = select_window(turns)
    base: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "no_coding_question",
        "solution_allowed": False,
        "input_format": input_format,
        "transcript_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "turn_count": len(turns),
        "selected_span": None,
        "problem_statement_draft": None,
        "candidates": [],
        "facts": {},
        "uncertainties": [],
        "clarifying_questions": [],
        "solver_prompt": None,
        "code_generation_contract": {"language": default_language, "forbid_code_until_ready": True, "required_sections": ["reconstructed_problem", "assumptions", "approach_and_invariant", "correctness", "complexity", "code", "focused_tests"]},
    }
    if not window or score < 3.2:
        base["uncertainties"] = ["No stable interviewer span met the coding-question threshold."]
        return base
    selected = clean(" ".join(turn.text for turn in window))[:MAX_SELECTED_CHARS]
    enriched = selected + (" Clarifications: " + " ".join(f"{key}: {value}" for key, value in sorted(answers.items())) if answers else "")
    candidates = rank_archetypes(enriched)
    if not candidates and score < 4.6:
        base["selected_span"] = {"text": selected, "coding_score": round(score, 3), "sources": source_refs(window)}
        base["uncertainties"] = ["The selected span has coding language but no stable problem archetype."]
        return base
    facts = extract_facts(enriched, answers)
    language = facts["language_detected"] or answers.get("language") or default_language
    questions = blocking_questions(candidates[0]["slug"] if candidates else None, facts, answers, candidates)
    uncertainties = [f"{item['title']} is an archetype hypothesis, not an established exact match." for item in candidates if item["match_kind"] != "likely_exact"]
    if not candidates:
        uncertainties.append("No exact LeetCode title is established; treat this as LeetCode-like only.")
    if questions:
        uncertainties.append("Blocking contract details remain unanswered; code generation is not authorized.")
    status = "needs_clarification" if questions else "ready_for_solution"
    base.update({
        "status": status,
        "solution_allowed": status == "ready_for_solution",
        "selected_span": {"text": selected, "coding_score": round(score, 3), "sources": source_refs(window)},
        "problem_statement_draft": selected[:1_800],
        "candidates": candidates,
        "facts": facts,
        "uncertainties": uncertainties,
        "clarifying_questions": questions,
        "solver_prompt": solver_prompt(selected[:1_800], candidates, facts, language) if status == "ready_for_solution" else None,
        "code_generation_contract": {**base["code_generation_contract"], "language": language},
    })
    return base


def parse_answers(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    candidate = raw
    try:
        path = Path(raw)
        if path.exists() and path.is_file():
            candidate = path.read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise InputError(f"answers must be a JSON object or path to one: {exc}") from exc
    if not isinstance(value, dict):
        raise InputError("answers must be a JSON object")
    return {str(key): clean(item)[:2_000] for key, item in value.items() if clean(item)}


def read_transcript(path_value: str) -> str:
    if path_value == "-":
        return sys.stdin.read()
    path = Path(path_value)
    if not path.is_file():
        raise InputError(f"transcript file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract likely LeetCode-style questions and blocking clarifications from a transcript.")
    parser.add_argument("transcript", help="Transcript path or '-' for stdin")
    parser.add_argument("--answers", help="JSON object or JSON file mapping clarification ids to answers")
    parser.add_argument("--language", default="Python 3", help="Default implementation language")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = analyze(read_transcript(args.transcript), parse_answers(args.answers), args.language)
        text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=None if args.compact else 2, separators=(",", ":") if args.compact else None) + "\n"
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    except (InputError, UnicodeError, OSError) as exc:
        print(json.dumps({"schema": SCHEMA, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
