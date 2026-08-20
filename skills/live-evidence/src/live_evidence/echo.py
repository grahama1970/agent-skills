"""Assistant echo redaction (#1453), split out of the coordinator."""

from __future__ import annotations


def strip_assistant_echo(text: str, assistant_utterances: list[str]) -> str:
    """Redact the assistant's own spoken content, keep everything else.

    Character-level fuzzy matching, not token identity: STT respells our
    own speech ("breakpoint" -> "break point", "forty two" -> "42",
    "set" -> "said"), so exact-token runs missed the echo entirely --
    observed live: the registered monologue survived redaction verbatim.
    difflib matching blocks of 15+ characters against each registered
    utterance are removed; genuinely human speech does not share long
    character runs with the assistant's script by accident.
    """

    if not assistant_utterances:
        return text
    import difflib

    # SequenceMatcher yields ONE monotone alignment, but cumulative STT
    # buffers can contain the same echoed phrase more than once -- the
    # second occurrence survived a single pass (observed live: the card
    # question repeated "point I set at line 42" twice). Iterate to a
    # fixed point, bounded.
    for iteration in range(6):
        lowered = text.lower()
        cut: list[tuple[int, int]] = []
        for utterance in assistant_utterances:
            matcher = difflib.SequenceMatcher(None, lowered, utterance, autojunk=False)
            for block in matcher.get_matching_blocks():
                if block.size >= 15:
                    cut.append((block.a, block.a + block.size))
        if not cut:
            if iteration == 0:
                return text  # nothing echoed: leave text untouched
            break
        cut.sort()
        # Expand each cut to word boundaries: a mid-word cut leaves
        # fragments like "oint" from "breakpoint" that later STT variance
        # turns into card text (observed live: "o the break 42").
        expanded: list[tuple[int, int]] = []
        for start, end in cut:
            while start > 0 and not text[start - 1].isspace():
                start -= 1
            while end < len(text) and not text[end].isspace():
                end += 1
            expanded.append((start, end))
        kept: list[str] = []
        cursor = 0
        for start, end in expanded:
            if start > cursor:
                kept.append(text[cursor:start])
            cursor = max(cursor, end)
        kept.append(text[cursor:])
        text = " ".join("".join(kept).split())
    # Scrub (reached only when something WAS cut): residual words fuzzily
    # matching assistant vocabulary are echo debris -- STT respells our
    # speech ("breakpoint" -> "break"/"oint.42"), so exact matching misses
    # exactly the debris that survives the character cuts.
    import re as _re

    vocabulary = {
        part
        for utterance in assistant_utterances
        for token in utterance.split()
        for part in _re.split(r"[^a-z0-9]+", token)
        if len(part) >= 4 or part.isdigit()
    }

    def is_debris(word: str) -> bool:
        parts = [p for p in _re.split(r"[^a-z0-9]+", word.lower()) if p]
        if not parts:
            return False
        def part_matches(part: str) -> bool:
            if part in vocabulary:
                return True
            if len(part) >= 4:
                return any(len(v) >= 5 and (part in v or v in part) for v in vocabulary)
            return False
        return all(part_matches(p) for p in parts)

    return " ".join(word for word in text.split() if not is_debris(word))

