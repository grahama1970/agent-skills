"""Needle-style registration without an execution loop or generated arguments.

A decorator preserves the original function. Candidate arguments must be provided
by trusted code and pass a strict Pydantic schema. The owner executes after policy
and state rechecks; this module never executes a selected candidate.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, get_type_hints
from pydantic import BaseModel, ConfigDict, create_model
from .core import fingerprint
from .routing import Candidate


class RegisteredTool:
    def __init__(self, fn: Callable, name: str, description: str, args_model: type[BaseModel]):
        self.fn, self.name, self.description, self.args_model = fn, name, description, args_model

    def candidate(self, *, candidate_id: str | None = None, **arguments: Any) -> Candidate:
        parsed = self.args_model.model_validate(arguments, strict=True)
        schema = self.args_model.model_json_schema()
        return Candidate(id=candidate_id or self.name, description=self.description,
                         payload={"tool": self.name, "arguments": parsed.model_dump(mode="json"),
                                  "argument_schema_hash": fingerprint(schema)})


def tool(*, name: str | None = None, description: str | None = None,
         args_model: type[BaseModel] | None = None):
    """Attach a registration as fn.jev; calling fn still calls the original function."""
    def decorate(fn: Callable) -> Callable:
        model = args_model
        if model is None:
            fields = {}
            hints = get_type_hints(fn)
            for key, param in inspect.signature(fn).parameters.items():
                if param.kind not in {param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY} or key not in hints:
                    raise ValueError("tool_requires_typed_keyword_bindings")
                fields[key] = (hints[key], ... if param.default is inspect.Parameter.empty else param.default)
            model = create_model(f"{fn.__name__}Arguments", __config__=ConfigDict(extra="forbid", strict=True), **fields)
        if model.model_config.get("extra") != "forbid":
            raise ValueError("tool_schema_must_forbid_extra")
        registration = RegisteredTool(fn, name or fn.__name__, description or inspect.getdoc(fn) or fn.__name__, model)
        # No wrapper and no hidden network request: preserve identity/signature.
        fn.jev = registration
        return fn
    return decorate


