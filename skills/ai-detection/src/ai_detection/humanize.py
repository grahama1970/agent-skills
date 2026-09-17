"""Red-team style-normalization humanizer and detector feature-fragility probe.

Purpose (R&D, mechanism-only): apply bounded, semantics-preserving style
transforms to Python source (the axis the literature flags as the softest to
evade: reformatting, comment stripping, whitespace normalization) and measure
how far each transform moves the detector's feature sub-views. This is the
first Battle "red move" and a blue-team weakness map.

Boundaries: transforms never execute submitted code (parse/AST only) and always
re-validate that the output still parses. A large feature-view delta here is a
DETECTOR FRAGILITY signal, NOT proof of evasion, authorship, or efficacy — a
verdict flip is only established by a trained model under Battle/Judge replay.
"""
import ast
import io
import tokenize
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from loguru import logger

from ai_detection.errors import Code, DetectionError
from ai_detection.features import HASH_WIDTH, extract

# Feature-vector layout from features.extract: [raw-hash | struct-hash | numeric].
_RAW = slice(0, HASH_WIDTH)
_STRUCT = slice(HASH_WIDTH, HASH_WIDTH * 2)
_NUMERIC = slice(HASH_WIDTH * 2, None)


class Transform(StrEnum):
    """Closed set of bounded style-normalization transforms (the fragile axis)."""

    AST_REFORMAT = "ast_reformat"      # canonical unparse: drops comments + all formatting
    STRIP_COMMENTS = "strip_comments"  # remove comments, keep code + layout
    COLLAPSE_BLANKS = "collapse_blanks"  # drop blank / trailing-whitespace lines
    STRIP_DOCSTRINGS = "strip_docstrings"  # remove docstrings (a stylometric AI tell; content-level)


def humanize(source: str, transform: Transform) -> str:
    """Apply one bounded style transform; re-validate the result parses.

    Never executes the input. Raises DetectionError(INVALID_INPUT) if the input
    or the produced output is not parseable Python, so a broken transform can
    never be passed off downstream as valid humanized code.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        raise DetectionError(Code.INVALID_INPUT, "Input is not parseable Python.") from exc

    if transform == Transform.AST_REFORMAT:
        result = ast.unparse(tree)
    elif transform == Transform.STRIP_COMMENTS:
        result = _strip_comments(source)
    elif transform == Transform.COLLAPSE_BLANKS:
        result = "\n".join(line.rstrip() for line in source.splitlines() if line.strip()) + "\n"
    elif transform == Transform.STRIP_DOCSTRINGS:
        result = ast.unparse(_strip_docstrings(tree))
    else:  # unreachable given the enum, but fail closed rather than silently pass through
        raise DetectionError(Code.INVALID_INPUT, f"Unknown transform: {transform!r}")

    try:
        ast.parse(result)
    except (SyntaxError, ValueError) as exc:
        logger.error("classified_failure module=humanize transform={}", transform.value)
        raise DetectionError(Code.INVALID_INPUT, "Humanized output no longer parses.") from exc
    return result


def _strip_docstrings(tree: ast.Module) -> ast.Module:
    """Drop leading string-literal docstrings from module/function/class bodies.

    Docstrings are non-functional, so removal preserves semantics; it is a
    content-level edit (unlike whitespace) that does move the structural view.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            # Keep at least a pass so an emptied body still parses.
            node.body = body[1:] or [ast.Pass()]
    return ast.fix_missing_locations(tree)


def _strip_comments(source: str) -> str:
    """Remove comment tokens while preserving code tokens and layout."""
    out = io.StringIO()
    tokens = (t for t in tokenize.generate_tokens(io.StringIO(source).readline)
              if t.type != tokenize.COMMENT)
    out.write(tokenize.untokenize(_regap(tokens)))
    return out.getvalue()


def _regap(tokens):
    """Yield tokens with 2-tuples so untokenize recomputes spacing after removals."""
    for tok in tokens:
        yield (tok.type, tok.string)


@dataclass(frozen=True, slots=True)
class Fragility:
    """One transform's effect on the detector feature sub-views."""

    transform: str
    full_cosine_distance: float
    raw_view_distance: float
    struct_view_distance: float
    numeric_view_distance: float
    normalized_digest_changed: bool
    token_count_before: int
    token_count_after: int


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0 if na == nb else 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def probe_fragility(source: str, transforms: list[Transform] | None = None) -> list[Fragility]:
    """Measure how far each transform moves each detector feature sub-view.

    A large raw_view_distance with a near-zero struct_view_distance and an
    unchanged normalized digest is the actionable finding: the detector's
    formatting-sensitive channel is fragile, its structural channel is not.
    """
    selected = transforms or list(Transform)
    before = extract(source)
    results: list[Fragility] = []
    for transform in selected:
        after = extract(humanize(source, transform))
        results.append(Fragility(
            transform=transform.value,
            full_cosine_distance=_cosine_distance(before.vector, after.vector),
            raw_view_distance=_cosine_distance(before.vector[_RAW], after.vector[_RAW]),
            struct_view_distance=_cosine_distance(before.vector[_STRUCT], after.vector[_STRUCT]),
            numeric_view_distance=_cosine_distance(before.vector[_NUMERIC], after.vector[_NUMERIC]),
            normalized_digest_changed=before.normalized_sha256 != after.normalized_sha256,
            token_count_before=before.token_count,
            token_count_after=after.token_count,
        ))
    return results
