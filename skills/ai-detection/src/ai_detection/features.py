"""Bounded Python multi-view features; parses but never executes submitted code."""
import ast
import hashlib
import io
import keyword
import math
import token
import tokenize
from dataclasses import dataclass

import numpy as np
from loguru import logger

from ai_detection.errors import Code, DetectionError
from ai_detection.io import text_digest

FEATURE_VERSION = "python-multiview-1"
HASH_WIDTH = 256
NUMERIC_WIDTH = 16
FEATURE_WIDTH = HASH_WIDTH * 2 + NUMERIC_WIDTH

@dataclass(frozen=True, slots=True)
class Views:
    vector: np.ndarray
    normalized_sha256: str
    token_count: int
    node_count: int


def _hash_view(items: list[str], width: int = HASH_WIDTH) -> np.ndarray:
    result = np.zeros(width, dtype=np.float64)
    for item in items:
        raw = hashlib.blake2b(item.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(raw[:4], "little") % width
        result[index] += 1.0 if raw[4] & 1 else -1.0
    norm = float(np.linalg.norm(result))
    return result / norm if norm else result


def extract(source: str, max_chars: int = 64000) -> Views:
    if not source.strip() or len(source) > max_chars:
        raise DetectionError(Code.INVALID_INPUT, "Empty or oversized Python input.")
    try:
        tree = ast.parse(source)
        nodes = list(ast.walk(tree))
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (SyntaxError, ValueError, tokenize.TokenError, RecursionError, UnicodeError) as exc:
        logger.error("classified_failure module=features")
        raise DetectionError(Code.INVALID_INPUT, "Python parsing failed; detection must abstain.") from exc
    if len(nodes) > 20000 or len(tokens) > 40000:
        raise DetectionError(Code.LIMIT, "Python structural complexity exceeds analysis bounds.")
    normalized: list[str] = []
    raw: list[str] = []
    comments = names = 0
    for item in tokens:
        if item.type in (token.ENDMARKER, tokenize.ENCODING):
            continue
        raw.append(f"{item.type}:{item.string}")
        if item.type == tokenize.COMMENT:
            comments += 1
            continue
        if item.type == token.NAME and not keyword.iskeyword(item.string):
            normalized.append("IDENT")
            names += 1
        elif item.type in (token.STRING, token.NUMBER):
            normalized.append(token.tok_name[item.type])
        elif item.type not in (token.NEWLINE, tokenize.NL, token.INDENT, token.DEDENT):
            normalized.append(item.string)
    # Normalization is a view and a conservative duplicate guard, not a semantic-equivalence proof.
    structure = [type(node).__name__ for node in nodes]
    ngrams = ["\x1f".join(normalized[i:i + 3]) for i in range(max(0, len(normalized) - 2))]
    lengths = [len(line) for line in source.splitlines()] or [0]
    count = max(1, len(nodes))
    numeric = [
        math.log1p(len(source)), math.log1p(len(tokens)), math.log1p(len(lengths)),
        float(np.mean(lengths)) / 100, float(np.std(lengths)) / 100,
        comments / max(1, len(tokens)), names / max(1, len(tokens)),
        len(set(normalized)) / max(1, len(normalized)),
    ]
    for node_type in (ast.FunctionDef, ast.If, ast.For, ast.While, ast.Try,
                      ast.ListComp, ast.Call, ast.Return):
        numeric.append(sum(isinstance(node, node_type) for node in nodes) / count)
    vector = np.concatenate((_hash_view(raw), _hash_view(ngrams + structure), np.array(numeric)))
    return Views(vector, text_digest("\x1f".join(normalized)), len(tokens), len(nodes))
