from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import torch


class _Tokenizer:
    def encode(self, text: str, add_special_tokens: bool) -> list[int]:
        assert text == "horus: State the evidence."
        assert add_special_tokens is True
        return [101, 102, 103]


def _load_module():
    sys.modules.setdefault("peft", types.SimpleNamespace(PeftModel=object))
    sys.modules.setdefault("snac", types.SimpleNamespace(SNAC=object))
    sys.modules.setdefault("unsloth", types.SimpleNamespace(FastLanguageModel=object))
    path = Path(__file__).parents[1] / "docker/inference_orpheus_unsloth.py"
    spec = importlib.util.spec_from_file_location("orpheus_inference_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_prompt_includes_official_end_of_text_boundary() -> None:
    module = _load_module()
    input_ids, attention_mask = module.build_prompt_input_ids(
        _Tokenizer(), speaker="horus", prompt="State the evidence."
    )
    assert input_ids.tolist() == [[
        module.START_OF_HUMAN,
        101,
        102,
        103,
        module.END_OF_TEXT,
        module.END_OF_HUMAN,
        module.START_OF_AI,
        module.START_OF_SPEECH,
    ]]
    assert torch.equal(attention_mask, torch.ones_like(input_ids))
