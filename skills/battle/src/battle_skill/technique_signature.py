"""Code-derived technique signatures and delta validation for Red exploits.

This module lets the orchestrator prove *objectively* that a child exploit is a
real mutation of its parent, independent of whatever the model claims. It is
pure Python-AST analysis of exploit source: no model calls, no network calls,
deterministic (same source string in -> byte-identical signature out).

Two receipts are produced:

``battle.technique_signature.v1``
    A normalized fingerprint of an exploit across exactly six dimensions, each
    derived from the parsed ``ast`` of the source plus normalized string
    literals. The source ``sha256`` is embedded so signatures are tamper-evident.

``battle.technique_delta_validation.v1``
    Compares a parent signature with a child signature and the child's claimed
    ``mutation_operator``. It fails closed: PASS only when the sources differ,
    at least one dimension changed, novelty distance >= 1, and the set of
    changed dimensions is consistent with the claimed operator.

Operator -> dimension consistency mapping (documented, deterministic):

    method_replace
        Replaces the *mechanism* used to reach the target. Consistent only when
        every changed dimension is in {app_load_mode, target_call_form}.
    oracle_or_parameter_mutation
        Mutates the success oracle or a payload parameter (the archive entry or
        the traversal string). Consistent only when every changed dimension is
        in {success_oracle, traversal_representation, archive_entry_construction}.
    failure_guided_crossover
        Blends multiple parent techniques after a failure. Any dimension may
        change, but a genuine crossover must move at least two dimensions, so
        consistent only when novelty_distance >= 2.

Any operator outside that vocabulary fails closed (operator_consistent=False).
"""

from __future__ import annotations

import ast
import hashlib
from typing import Any

SIGNATURE_SCHEMA = "battle.technique_signature.v1"
DELTA_SCHEMA = "battle.technique_delta_validation.v1"
POLICY_ID = "battle-technique-signature-ast-v1"

DIMENSIONS: tuple[str, ...] = (
    "app_load_mode",
    "archive_entry_construction",
    "traversal_representation",
    "target_call_form",
    "success_oracle",
    "exception_handling",
)

MUTATION_OPERATORS: tuple[str, ...] = (
    "method_replace",
    "oracle_or_parameter_mutation",
    "failure_guided_crossover",
)

# Operator -> dimensions that operator is allowed to move. The
# failure_guided_crossover operator may move any dimension but is validated by
# novelty distance instead of a dimension whitelist (see docstring).
OPERATOR_DIMENSIONS: dict[str, frozenset[str]] = {
    "method_replace": frozenset({"app_load_mode", "target_call_form"}),
    "oracle_or_parameter_mutation": frozenset(
        {"success_oracle", "traversal_representation", "archive_entry_construction"}
    ),
    "failure_guided_crossover": frozenset(DIMENSIONS),
}
CROSSOVER_MIN_NOVELTY = 2


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _string_constants(tree: ast.AST) -> list[str]:
    """Every string literal in the tree, in source order (deterministic)."""
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def _attr_chain(node: ast.AST) -> str:
    """Dotted attribute/name chain for a call target, e.g. ``a.b.c``."""
    parts: list[str] = []
    cur: ast.AST | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _calls(tree: ast.AST) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _derive_app_load_mode(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            chain = _attr_chain(node.func)
            if chain.endswith("spec_from_file_location"):
                return "importlib_spec_from_file"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                return "dunder_import"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "app":
            return "from_import_app"
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app" or alias.name.startswith("app."):
                    return "plain_import_app"
    return "none"


def _derive_archive_entry_construction(tree: ast.AST) -> str:
    tokens: set[str] = set()
    for call in _calls(tree):
        chain = _attr_chain(call.func)
        method = chain.rsplit(".", 1)[-1] if chain else ""
        kwargs = {kw.arg for kw in call.keywords if kw.arg}
        if method == "writestr":
            tokens.add("zipfile_writestr")
        elif method == "write" and ("arcname" in kwargs or _looks_like_zip(chain)):
            tokens.add("zipfile_write_arcname" if "arcname" in kwargs else "zipfile_write")
        elif chain.endswith("ZipInfo") or method == "ZipInfo":
            tokens.add("zipinfo")
        elif method in {"addfile", "add"} and "tar" in chain.lower():
            tokens.add("tarfile_add")
    if not tokens:
        return "none"
    return "+".join(sorted(tokens))


def _looks_like_zip(chain: str) -> bool:
    lowered = chain.lower()
    return "zip" in lowered or "archive" in lowered


def _derive_traversal_representation(tree: ast.AST) -> str:
    tokens: set[str] = set()
    for literal in _string_constants(tree):
        if "../" in literal or literal == ".." or literal.startswith("../"):
            tokens.add("dotdot_relative")
        if "..\\" in literal:
            tokens.add("dotdot_windows")
        if literal.startswith("/") and len(literal) > 1:
            tokens.add("absolute_path")
    for call in _calls(tree):
        chain = _attr_chain(call.func)
        if chain.endswith("symlink"):
            tokens.add("symlink")
        if chain.endswith("os.path.join") or chain.endswith("path.join"):
            tokens.add("ospath_join")
    if not tokens:
        return "none"
    return "+".join(sorted(tokens))


def _derive_target_call_form(tree: ast.AST) -> str:
    tokens: set[str] = set()
    imported_targets = _imported_target_names(tree)
    for call in _calls(tree):
        chain = _attr_chain(call.func)
        method = chain.rsplit(".", 1)[-1] if chain else ""
        root = chain.split(".", 1)[0] if chain else ""
        if root in {"httpx", "requests"} or root in {"client", "session"}:
            if method in {"post", "get", "put", "delete", "request"}:
                tokens.add(f"http_{method}")
        if method in {"run", "check_output", "Popen", "call"} and (
            "subprocess" in chain
        ):
            tokens.add("cli_subprocess")
        if isinstance(call.func, ast.Name) and call.func.id in imported_targets:
            tokens.add("function_call")
    if not tokens:
        return "none"
    return "+".join(sorted(tokens))


def _imported_target_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "app":
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _derive_success_oracle(tree: ast.AST) -> str:
    tokens: set[str] = set()
    for call in _calls(tree):
        chain = _attr_chain(call.func)
        method = chain.rsplit(".", 1)[-1] if chain else ""
        if method == "exists" or chain.endswith("os.path.exists"):
            tokens.add("file_existence")
        if method == "is_file":
            tokens.add("file_existence")
        if method in {"read_text", "read_bytes"}:
            tokens.add("file_read_back")
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            tokens.add("assertion")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "print":
                for arg in _string_constants(node):
                    for word in arg.replace("=", " ").split():
                        if word.isupper() and len(word) >= 4:
                            tokens.add("printed_marker")
    if not tokens:
        return "none"
    return "+".join(sorted(tokens))


def _derive_exception_handling(tree: ast.AST) -> str:
    handlers: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                caught = _handler_type(handler)
                body_kind = _handler_body_kind(handler)
                handlers.append(f"{caught}:{body_kind}")
    if not handlers:
        return "none"
    return "try[" + "|".join(sorted(handlers)) + "]"


def _handler_type(handler: ast.ExceptHandler) -> str:
    exc = handler.type
    if exc is None:
        return "bare"
    if isinstance(exc, ast.Name):
        return exc.id
    if isinstance(exc, ast.Tuple):
        parts = [e.id for e in exc.elts if isinstance(e, ast.Name)]
        return "(" + ",".join(sorted(parts)) + ")"
    return _attr_chain(exc) or "unknown"


def _handler_body_kind(handler: ast.ExceptHandler) -> str:
    body = handler.body
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return "suppress"
    for stmt in body:
        if isinstance(stmt, ast.Raise):
            return "reraise"
        if isinstance(stmt, ast.Return):
            return "return"
    return "handle"


def technique_signature(source: str) -> dict[str, Any]:
    """Derive a ``battle.technique_signature.v1`` from exploit source.

    Deterministic: the same ``source`` string always yields a byte-identical
    dict. If the source does not parse, every dimension is ``"unparsable"`` and
    ``parse_ok`` is False (fail-closed, still hashable/comparable).
    """
    sha = _sha256_text(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        dimensions = {name: "unparsable" for name in DIMENSIONS}
        return {
            "schema": SIGNATURE_SCHEMA,
            "policy_id": POLICY_ID,
            "sha256": sha,
            "parse_ok": False,
            "dimensions": dimensions,
        }
    dimensions = {
        "app_load_mode": _derive_app_load_mode(tree),
        "archive_entry_construction": _derive_archive_entry_construction(tree),
        "traversal_representation": _derive_traversal_representation(tree),
        "target_call_form": _derive_target_call_form(tree),
        "success_oracle": _derive_success_oracle(tree),
        "exception_handling": _derive_exception_handling(tree),
    }
    return {
        "schema": SIGNATURE_SCHEMA,
        "policy_id": POLICY_ID,
        "sha256": sha,
        "parse_ok": True,
        "dimensions": {name: dimensions[name] for name in DIMENSIONS},
    }


def _operator_consistent(
    operator: str, changed: list[str], novelty_distance: int
) -> tuple[bool, str]:
    if operator not in MUTATION_OPERATORS:
        return False, f"operator '{operator}' is not in the allowed vocabulary"
    if novelty_distance < 1 or not changed:
        return False, "no dimensions changed, so the operator cannot be consistent"
    if operator == "failure_guided_crossover":
        if novelty_distance >= CROSSOVER_MIN_NOVELTY:
            return True, "crossover moved at least two dimensions"
        return (
            False,
            "failure_guided_crossover requires >= "
            f"{CROSSOVER_MIN_NOVELTY} changed dimensions, got {novelty_distance}",
        )
    allowed = OPERATOR_DIMENSIONS[operator]
    outside = sorted(set(changed) - allowed)
    if outside:
        return (
            False,
            f"operator '{operator}' cannot change dimensions {outside}; "
            f"allowed: {sorted(allowed)}",
        )
    return True, f"all changed dimensions are allowed for operator '{operator}'"


def validate_technique_delta(
    *,
    parent_signature: dict[str, Any],
    child_signature: dict[str, Any],
    mutation_operator: str,
    battle_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build a ``battle.technique_delta_validation.v1`` receipt (fail-closed).

    PASS only when ALL hold: parent/child source sha256 differ, at least one of
    the six dimensions changed, novelty_distance >= 1, and the changed
    dimensions are consistent with ``mutation_operator``. Any other case is FAIL
    with explicit ``reasons``.
    """
    parent_sha = parent_signature.get("sha256")
    child_sha = child_signature.get("sha256")
    parent_dims = parent_signature.get("dimensions", {}) or {}
    child_dims = child_signature.get("dimensions", {}) or {}

    per_dimension = []
    changed: list[str] = []
    for name in DIMENSIONS:
        p_val = parent_dims.get(name)
        c_val = child_dims.get(name)
        is_changed = p_val != c_val
        if is_changed:
            changed.append(name)
        per_dimension.append(
            {
                "dimension": name,
                "parent": p_val,
                "child": c_val,
                "changed": is_changed,
            }
        )
    novelty_distance = len(changed)

    reasons: list[str] = []
    sha_differ = bool(parent_sha) and bool(child_sha) and parent_sha != child_sha
    if not sha_differ:
        reasons.append(
            "parent and child source sha256 are equal or missing "
            f"(parent={parent_sha}, child={child_sha})"
        )
    if novelty_distance < 1:
        reasons.append("no technique dimension changed (novelty_distance=0)")

    operator_consistent, operator_reason = _operator_consistent(
        mutation_operator, changed, novelty_distance
    )
    if not operator_consistent:
        reasons.append(operator_reason)

    status = "PASS" if (sha_differ and novelty_distance >= 1 and operator_consistent) else "FAIL"
    if status == "PASS":
        reasons.append(operator_reason)

    return {
        "schema": DELTA_SCHEMA,
        "policy_id": POLICY_ID,
        "status": status,
        "battle_id": battle_id,
        "run_id": run_id,
        "claimed_mutation_operator": mutation_operator,
        "operator_in_vocabulary": mutation_operator in MUTATION_OPERATORS,
        "parent_sha256": parent_sha,
        "child_sha256": child_sha,
        "sha256_differ": sha_differ,
        "per_dimension": per_dimension,
        "changed_dimensions": changed,
        "unchanged_dimensions": [d for d in DIMENSIONS if d not in changed],
        "novelty_distance": novelty_distance,
        "operator_consistent": operator_consistent,
        "reasons": reasons,
    }
