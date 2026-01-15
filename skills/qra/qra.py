#!/usr/bin/env python3
"""QRA (Question-Reasoning-Answer) knowledge extraction skill.

Extracts grounded QRA pairs from text using parallel LLM calls.
Supports domain-specific context for focused extraction.

Usage:
    python qra.py --text "large text..." --scope research
    python qra.py --file doc.md --context "cybersecurity expert"
    cat text.txt | python qra.py --scope myproject
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# Best-effort .env loading
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:
    pass

# =============================================================================
# Rich/tqdm Progress Indicators (optional, graceful fallback)
# =============================================================================

_HAS_RICH = False
_HAS_TQDM = False
_console = None

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich.table import Table
    _HAS_RICH = True
    _console = Console(stderr=True)
except ImportError:
    pass

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    pass


def _log(msg: str, style: str = None):
    """Log message with optional rich styling."""
    if _HAS_RICH and _console:
        _console.print(f"[dim][qra][/dim] {msg}", style=style)
    else:
        print(f"[qra] {msg}", file=sys.stderr)


def _status_panel(title: str, content: Dict[str, Any]):
    """Display a rich status panel if available."""
    if _HAS_RICH and _console:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        for k, v in content.items():
            table.add_row(str(k), str(v))
        _console.print(Panel(table, title=f"[bold]{title}[/bold]", border_style="blue"))
    else:
        print(f"[qra] {title}:", file=sys.stderr)
        for k, v in content.items():
            print(f"  {k}: {v}", file=sys.stderr)


def _iter_with_progress(iterable, desc: str = "Processing", total: int = None):
    """Iterate with progress bar (tqdm or rich fallback)."""
    if total is None:
        try:
            total = len(iterable)
        except TypeError:
            pass

    if _HAS_TQDM and not _HAS_RICH:
        return tqdm(iterable, desc=f"[qra] {desc}", total=total, file=sys.stderr)
    elif _HAS_RICH and _console:
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=_console,
        )
        task_id = progress.add_task(desc, total=total or 0)

        def gen():
            with progress:
                for item in iterable:
                    yield item
                    progress.advance(task_id)
        return gen()
    # Fallback
    def gen():
        for i, item in enumerate(iterable):
            if total and i % max(1, total // 10) == 0:
                print(f"[qra] {desc}: {i}/{total}", file=sys.stderr)
            yield item
    return gen()


# =============================================================================
# Sentence Splitting
# =============================================================================

_ABBREVS = {
    "fig", "sec", "no", "dr", "mr", "mrs", "ms", "prof",
    "u.s", "u.k", "dept", "inc", "ltd", "vs", "etc", "e.g", "i.e", "cf", "al"
}


def split_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    if not text or not text.strip():
        return []

    try:
        from nltk.tokenize import PunktSentenceTokenizer
        tok = PunktSentenceTokenizer()
        tok._params.abbrev_types.update({a.replace(".", "") for a in _ABBREVS})
        sents = [t.strip() for t in tok.tokenize(text) if t.strip()]
        if sents:
            return sents
    except Exception:
        pass

    # Fallback: regex split
    sents = re.split(r'(?<=[.!?])\s+(?=[A-Z(])', text)
    return [s.strip() for s in sents if s.strip()]


# =============================================================================
# Section Building
# =============================================================================

def build_sections(
    text: str,
    max_section_chars: int = 5000,
) -> List[Tuple[str, str]]:
    """Build sections from text, respecting document structure.

    Returns list of (section_title, section_content) tuples.
    """
    # Simple section splitting by markdown headers or paragraph breaks
    lines = text.split('\n')
    sections: List[Tuple[str, str]] = []

    current_title = ""
    current_content: List[str] = []

    # Pattern for markdown headers
    header_re = re.compile(r'^(#{1,6})\s+(.+)$')
    # Pattern for numbered sections
    numbered_re = re.compile(r'^\s*(\d+(?:\.\d+)*)\s*[.:)\-]?\s+(\S.*)$')

    for line in lines:
        # Check for headers
        m = header_re.match(line)
        if m:
            # Save previous section
            if current_content:
                content = '\n'.join(current_content).strip()
                if content:
                    sections.append((current_title, content))
            current_title = m.group(2).strip()
            current_content = []
            continue

        m = numbered_re.match(line)
        if m and len(m.group(2)) > 10:  # Avoid matching simple numbers
            if current_content:
                content = '\n'.join(current_content).strip()
                if content:
                    sections.append((current_title, content))
            current_title = m.group(2).strip()
            current_content = []
            continue

        current_content.append(line)

    # Don't forget last section
    if current_content:
        content = '\n'.join(current_content).strip()
        if content:
            sections.append((current_title, content))

    # If no structure detected, return as single section
    if not sections:
        return [("", text)]

    # Split oversized sections
    result: List[Tuple[str, str]] = []
    for title, content in sections:
        if len(content) <= max_section_chars:
            result.append((title, content))
        else:
            # Split at sentence boundaries
            sents = split_sentences(content)
            chunk_sents: List[str] = []
            chunk_chars = 0
            part_num = 1

            for sent in sents:
                if chunk_chars + len(sent) > max_section_chars and chunk_sents:
                    chunk_title = f"{title} (part {part_num})" if title else f"Part {part_num}"
                    result.append((chunk_title, " ".join(chunk_sents)))
                    part_num += 1
                    chunk_sents = []
                    chunk_chars = 0

                chunk_sents.append(sent)
                chunk_chars += len(sent) + 1

            if chunk_sents:
                chunk_title = f"{title} (part {part_num})" if title and part_num > 1 else title
                result.append((chunk_title, " ".join(chunk_sents)))

    return result


# =============================================================================
# QRA Prompts with Domain Context Support
# =============================================================================

def build_system_prompt(context: Optional[str] = None) -> str:
    """Build QRA system prompt with optional domain context."""
    base_prompt = """You are a knowledge extraction assistant. You MUST respond with valid JSON only.
Do not include any text before or after the JSON. Do not use markdown code blocks.
Return ONLY a JSON object matching this exact schema:

{{"items": [
  {{"question": "string", "reasoning": "string", "answer": "string"}},
  ...
]}}

CRITICAL RULES:
- Extract ALL meaningful facts, concepts, and relationships from the text
- GROUNDING: Every answer MUST be directly supported by text in the source. Do NOT hallucinate.
- question: A clear, specific question that the text answers
- reasoning: Brief explanation of where/how the answer is found in the text
- answer: The factual answer, using words from the source text when possible
- Include as many items as the text supports (could be 1 to 50+)
- If text is too short, garbled, or lacks factual content, return {{"items": []}}
- Prefer extracting: definitions, methods, results, comparisons, key findings
"""

    if context:
        # Prepend domain context
        context_section = f"""You are a {context}.

Extract knowledge items that are relevant to your expertise and domain.
Skip content that is outside your area of focus.
Prioritize information that would be valuable to someone with your background.

"""
        return context_section + base_prompt

    return base_prompt


QRA_USER_PROMPT = """Extract all grounded knowledge items from this text. Every answer must be supported by the source text.

Text:
{text}

JSON:"""


# =============================================================================
# scillm Configuration
# =============================================================================

def _get_scillm_config() -> Dict[str, str]:
    """Get scillm configuration from environment."""
    model = (
        os.getenv("CHUTES_TEXT_MODEL")
        or os.getenv("SCILLM_DEFAULT_MODEL")
        or os.getenv("CHUTES_MODEL_ID", "deepseek/deepseek-chat")
    )
    return {
        "model": model,
        "api_base": os.getenv("CHUTES_API_BASE", "https://llm.chutes.ai/v1"),
        "api_key": os.getenv("CHUTES_API_KEY", ""),
    }


# =============================================================================
# Grounding Validation
# =============================================================================

def check_grounding(
    qra_items: List[Dict[str, Any]],
    sections: List[Tuple[str, str]],
    threshold: float = 0.6,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Validate QRA answers are grounded in source text.

    Uses rapidfuzz for fuzzy matching. Only validates answers (not questions)
    since questions can be phrased many ways but answers must be grounded.

    Args:
        qra_items: List of QRA dicts with section_idx
        sections: Original sections for lookup
        threshold: Minimum similarity score (0-1)

    Returns:
        Tuple of (grounded_items, kept_count, filtered_count)
    """
    try:
        from rapidfuzz import fuzz
        use_rapidfuzz = True
    except ImportError:
        use_rapidfuzz = False
        _log("rapidfuzz not available, using word overlap", style="dim")

    grounded = []
    filtered = 0

    for item in qra_items:
        section_idx = item.get("section_idx", 0)
        if section_idx >= len(sections):
            grounded.append(item)
            continue

        source_text = sections[section_idx][1].lower()
        answer = item.get("answer", "").lower()

        if not answer:
            filtered += 1
            continue

        if use_rapidfuzz:
            score = fuzz.token_set_ratio(answer, source_text) / 100.0
        else:
            # Word overlap fallback
            answer_words = set(answer.split())
            source_words = set(source_text.split())
            if answer_words:
                score = len(answer_words & source_words) / len(answer_words)
            else:
                score = 0.0

        if score >= threshold:
            item["grounding_score"] = round(score, 2)
            grounded.append(item)
        else:
            filtered += 1

    return grounded, len(grounded), filtered


# =============================================================================
# Batch QRA Extraction
# =============================================================================

def _parse_qra_response(
    content,
    section_idx: int,
    section_title: str,
    source: str,
    clean_json_fn,
) -> List[Dict[str, Any]]:
    """Parse LLM JSON response into QRA dicts."""
    try:
        if isinstance(content, dict):
            data = content
        else:
            cleaned = clean_json_fn(content) if clean_json_fn else content
            data = json.loads(cleaned)

        items = data.get("items", []) if isinstance(data, dict) else []
        if not items and isinstance(data, list):
            items = data
        if not items and isinstance(data, dict) and "question" in data:
            items = [data]

        result = []
        for item in items:
            if item.get("question") and item.get("answer"):
                problem = item["question"]
                if section_title:
                    problem = f"[{section_title}] {problem}"

                reasoning = item.get("reasoning", "")
                answer = item["answer"]
                solution = f"**Reasoning:** {reasoning}\n\n**Answer:** {answer}" if reasoning else answer

                result.append({
                    "problem": problem,
                    "solution": solution,
                    "question": item["question"],
                    "reasoning": reasoning,
                    "answer": answer,
                    "section_idx": section_idx,
                    "section_title": section_title,
                    "source": source,
                })
        return result
    except json.JSONDecodeError as e:
        _log(f"JSON parse error: {e}", style="yellow")
        return []
    except Exception as e:
        _log(f"Parse error: {e}", style="yellow")
        return []


def _heuristic_fallback(content: str, section_title: str, source: str) -> List[Dict[str, Any]]:
    """Simple heuristic extraction when LLM fails."""
    if not content.strip():
        return []

    if section_title:
        problem = f"What is {section_title}?" if not section_title.endswith("?") else section_title
    else:
        sents = split_sentences(content)
        problem = sents[0][:200] if sents else "Unknown topic"

    solution = content[:1000] if len(content) > 1000 else content

    return [{
        "problem": f"[{source}] {problem}" if source else problem,
        "solution": solution,
        "question": problem,
        "reasoning": "",
        "answer": solution,
        "source": source,
    }]


async def extract_qra_batch(
    sections: List[Tuple[str, str]],
    source: str = "",
    context: Optional[str] = None,
    concurrency: int = 6,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    """Extract QRA from sections using parallel LLM calls.

    Args:
        sections: List of (title, content) tuples
        source: Source identifier
        context: Optional domain context/persona
        concurrency: Max parallel requests
        timeout: Per-request timeout

    Returns:
        List of QRA dicts
    """
    config = _get_scillm_config()

    if not config["api_key"]:
        _log("CHUTES_API_KEY not set, using heuristic fallback", style="yellow")
        all_qa = []
        for idx, (title, content) in enumerate(sections):
            qras = _heuristic_fallback(content, title, source)
            for qra in qras:
                qra["section_idx"] = idx
                qra["section_title"] = title
            all_qa.extend(qras)
        return all_qa

    # Import scillm batch function
    batch_acompletions_iter = None
    clean_json_string = None

    try:
        from scillm.batch import parallel_acompletions_iter as batch_acompletions_iter
        from scillm.extras.json_utils import clean_json_string
    except ImportError:
        try:
            from scillm import batch_acompletions_iter
            from scillm.extras.json_utils import clean_json_string
        except ImportError:
            pass

    if batch_acompletions_iter is None:
        _log("scillm not available, using heuristic fallback", style="yellow")
        all_qa = []
        for idx, (title, content) in enumerate(sections):
            qras = _heuristic_fallback(content, title, source)
            for qra in qras:
                qra["section_idx"] = idx
                qra["section_title"] = title
            all_qa.extend(qras)
        return all_qa

    if clean_json_string is None:
        def clean_json_string(s: str) -> str:
            s = s.strip()
            if s.startswith("```json"):
                s = s[7:]
            if s.startswith("```"):
                s = s[3:]
            if s.endswith("```"):
                s = s[:-3]
            return s.strip()

    # Build system prompt with optional context
    system_prompt = build_system_prompt(context)
    system_msg = {"role": "system", "content": system_prompt}

    # Build requests
    requests = []
    metadata = []

    for idx, (section_title, section_content) in enumerate(sections):
        user_prompt = QRA_USER_PROMPT.format(text=section_content[:3000])
        requests.append({
            "model": config["model"],
            "messages": [system_msg, {"role": "user", "content": user_prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "temperature": 0.1,
        })
        metadata.append({"idx": idx, "title": section_title, "content": section_content})

    _log(f"Batch: {len(requests)} sections, concurrency={concurrency}")
    if context:
        _log(f"Context: {context[:60]}...", style="cyan")

    all_qa: List[Dict[str, Any]] = []
    done = ok = err = 0

    async for ev in batch_acompletions_iter(
        requests,
        api_base=config["api_base"],
        api_key=config["api_key"],
        custom_llm_provider="openai_like",
        concurrency=concurrency,
        timeout=timeout,
        wall_time_s=900,
        tenacious=True,
    ):
        done += 1
        req_idx = ev.get("index", done - 1)
        meta = metadata[req_idx] if req_idx < len(metadata) else {"idx": req_idx, "title": "", "content": ""}
        section_idx = meta["idx"]
        section_title = meta["title"]

        if ev.get("ok") and ev.get("content"):
            ok += 1
            qa_items = _parse_qra_response(
                ev["content"], section_idx, section_title, source, clean_json_string
            )
            if qa_items:
                all_qa.extend(qa_items)
                _log(f"[{done}/{len(requests)}] '{section_title[:30]}' -> {len(qa_items)} QRAs", style="green")
            else:
                # Fallback
                fallback = _heuristic_fallback(meta["content"], section_title, source)
                for fb in fallback:
                    fb["section_idx"] = section_idx
                    fb["section_title"] = section_title
                all_qa.extend(fallback)
                _log(f"[{done}/{len(requests)}] '{section_title[:30]}' -> heuristic fallback", style="yellow")
        else:
            err += 1
            _log(f"[{done}/{len(requests)}] '{section_title[:30]}' -> error", style="red")
            fallback = _heuristic_fallback(meta["content"], section_title, source)
            for fb in fallback:
                fb["section_idx"] = section_idx
                fb["section_title"] = section_title
            all_qa.extend(fallback)

    _log(f"Batch complete: {ok} ok, {err} errors, {len(all_qa)} QRAs", style="bold")
    return all_qa


# =============================================================================
# Memory Integration
# =============================================================================

def store_qra(qra: Dict[str, Any], scope: str, tags: List[str] = None) -> bool:
    """Store QRA pair via memory-agent learn."""
    cmd = [
        "memory-agent", "learn",
        "--problem", qra.get("problem", qra.get("question", "")),
        "--solution", qra.get("solution", qra.get("answer", "")),
        "--scope", scope,
    ]
    all_tags = ["qra", "distilled"]
    if tags:
        all_tags.extend(tags)
    for tag in all_tags:
        cmd.extend(["--tag", tag])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        _log(f"Store failed: {e}", style="red")
        return False


# =============================================================================
# Main Extract Function
# =============================================================================

def extract_qra(
    *,
    text: str = None,
    file_path: str = None,
    scope: str = "research",
    context: str = None,
    context_file: str = None,
    max_section_chars: int = 5000,
    dry_run: bool = False,
    concurrency: int = 6,
    validate_grounding: bool = True,
    grounding_threshold: float = 0.6,
) -> Dict[str, Any]:
    """Extract QRA pairs from text.

    Args:
        text: Text content to extract from
        file_path: File to read text from
        scope: Memory scope for storage
        context: Domain context/persona for focused extraction
        context_file: Read context from file
        max_section_chars: Max chars per section
        dry_run: Show QRAs without storing
        concurrency: Parallel LLM requests
        validate_grounding: Filter ungrounded answers
        grounding_threshold: Min similarity (0-1)

    Returns:
        Summary dict with extracted QRAs
    """
    import asyncio

    # Get text content
    if file_path:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        source = Path(file_path).name
    elif text:
        source = "text"
    else:
        # Try stdin
        if not sys.stdin.isatty():
            text = sys.stdin.read()
            source = "stdin"
        else:
            raise ValueError("Must provide --text, --file, or pipe content")

    if not text.strip():
        return {"extracted": 0, "stored": 0, "error": "Empty content"}

    # Get context from file if specified
    if context_file:
        context = Path(context_file).read_text(encoding="utf-8").strip()

    _status_panel("QRA Extraction", {
        "Source": source,
        "Content": f"{len(text):,} chars",
        "Context": (context[:40] + "...") if context else "(none)",
        "Scope": scope,
    })

    # Build sections
    sections = build_sections(text, max_section_chars=max_section_chars)
    _log(f"Split into {len(sections)} sections")

    # Extract QRAs
    all_qa = asyncio.run(
        extract_qra_batch(
            sections,
            source=source,
            context=context,
            concurrency=concurrency,
        )
    )

    _log(f"Extracted {len(all_qa)} QRAs", style="bold")

    # Grounding validation
    if validate_grounding and all_qa:
        all_qa, kept, filtered = check_grounding(all_qa, sections, grounding_threshold)
        if filtered > 0:
            _log(f"Grounding: {kept} kept, {filtered} filtered (threshold={grounding_threshold})", style="yellow")
        else:
            _log(f"Grounding: all {kept} validated", style="green")

    # Store or dry-run
    stored = 0
    if dry_run:
        _log(f"DRY RUN - would store {len(all_qa)} QRAs", style="yellow")
    else:
        _log(f"Storing {len(all_qa)} QRAs to scope '{scope}'")
        tags = [source.split("/")[0] if "/" in source else source]
        for qra in _iter_with_progress(all_qa, desc="Storing"):
            if store_qra(qra, scope, tags=tags):
                stored += 1

    _status_panel("QRA Complete", {
        "Extracted": len(all_qa),
        "Stored": stored if not dry_run else "(dry run)",
        "Sections": len(sections),
    })

    return {
        "extracted": len(all_qa),
        "stored": stored,
        "sections": len(sections),
        "source": source,
        "scope": scope,
        "qra_pairs": all_qa if dry_run else all_qa[:5],
    }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract Question-Reasoning-Answer pairs from text",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file document.md --scope research
  %(prog)s --file notes.txt --context "security expert" --dry-run
  cat transcript.txt | %(prog)s --scope meetings

Environment variables for tuning (optional):
  QRA_CONCURRENCY       Parallel LLM requests (default: 6)
  QRA_GROUNDING_THRESH  Grounding similarity threshold (default: 0.6)
  QRA_NO_GROUNDING      Set to 1 to skip grounding validation
"""
    )

    # === Essential flags (agent-facing) ===
    parser.add_argument("--file", dest="file_path", help="Text/markdown file to extract from")
    parser.add_argument("--text", help="Raw text to extract from")
    parser.add_argument("--scope", default="research", help="Memory scope (default: research)")
    parser.add_argument("--context", help="Domain focus, e.g. 'ML researcher' or 'security expert'")
    parser.add_argument("--dry-run", action="store_true", help="Preview QRAs without storing to memory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    # === Hidden expert flags (use env vars instead) ===
    parser.add_argument("--context-file", dest="context_file", help=argparse.SUPPRESS)
    parser.add_argument("--max-section-chars", type=int, default=5000, help=argparse.SUPPRESS)
    parser.add_argument("--concurrency", type=int,
                        default=int(os.getenv("QRA_CONCURRENCY", "6")), help=argparse.SUPPRESS)
    parser.add_argument("--validate-grounding", dest="validate_grounding", action="store_true",
                        default=not os.getenv("QRA_NO_GROUNDING"), help=argparse.SUPPRESS)
    parser.add_argument("--no-validate-grounding", dest="validate_grounding",
                        action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("--grounding-threshold", type=float,
                        default=float(os.getenv("QRA_GROUNDING_THRESH", "0.6")), help=argparse.SUPPRESS)

    args = parser.parse_args()

    try:
        result = extract_qra(
            text=args.text,
            file_path=args.file_path,
            scope=args.scope,
            context=args.context,
            context_file=args.context_file,
            max_section_chars=args.max_section_chars,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
            validate_grounding=args.validate_grounding,
            grounding_threshold=args.grounding_threshold,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Extracted: {result['extracted']} QRAs from {result['sections']} sections")
            print(f"Stored: {result['stored']} in scope '{result['scope']}'")
            if result.get("qra_pairs"):
                print("\nSample QRAs:")
                for qra in result["qra_pairs"][:2]:
                    print(f"  Q: {qra.get('question', qra.get('problem', ''))[:70]}...")
                    print(f"  A: {qra.get('answer', qra.get('solution', ''))[:70]}...")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
