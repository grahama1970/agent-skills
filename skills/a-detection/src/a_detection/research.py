"""Optional local-only contrastive likelihood research; never an uncalibrated verdict."""
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import Field
from scipy.special import log_softmax

from a_detection.contracts import Sha256, Strict
from a_detection.errors import Code, DetectionError
from a_detection.io import canonical, digest, text_digest


class ReferenceRequest(Strict):
    source: str = Field(min_length=1, max_length=64000)
    model_a: str = Field(min_length=1, max_length=4096)
    model_b: str = Field(min_length=1, max_length=4096)
    model_a_manifest_sha256: Sha256
    model_b_manifest_sha256: Sha256
    device: Literal["cpu", "cuda"] = "cpu"
    max_tokens: int = Field(default=512, ge=8, le=2048)

class ContrastiveResult(Strict):
    schema_version: Literal["a_detection.contrastive_score.v1"] = "a_detection.contrastive_score.v1"
    source_sha256: Sha256
    model_a_manifest_sha256: Sha256
    model_b_manifest_sha256: Sha256
    score: float = Field(ge=0)
    nll_a: float = Field(ge=0)
    cross_entropy_a_b: float = Field(gt=0)
    scored_tokens: int = Field(ge=1)
    complete_input: Literal[True] = True
    classification: Literal["UNCALIBRATED_RESEARCH_SIGNAL"] = "UNCALIBRATED_RESEARCH_SIGNAL"


def contrastive_math(logits_a: np.ndarray, logits_b: np.ndarray,
                     next_token_ids: np.ndarray) -> tuple[float, float, float]:
    """Equation-4-style NLL(A)/CE(A,B), with explicit causal shift done by the caller."""
    if logits_a.ndim != 2 or logits_a.shape != logits_b.shape or len(logits_a) == 0:
        raise DetectionError(Code.INVALID_INPUT, "Reference logits must have matching nonempty [T,V] shapes.")
    if next_token_ids.shape != (len(logits_a),) or not np.issubdtype(next_token_ids.dtype, np.integer):
        raise DetectionError(Code.INVALID_INPUT, "Targets must be one integer token ID per logit row.")
    if (not np.isfinite(logits_a).all() or not np.isfinite(logits_b).all()
            or np.any(next_token_ids < 0) or np.any(next_token_ids >= logits_a.shape[1])):
        raise DetectionError(Code.INVALID_INPUT, "Invalid logits or target IDs.")
    a, b = log_softmax(logits_a.astype(np.float64), axis=-1), log_softmax(logits_b.astype(np.float64), axis=-1)
    nll = float(-a[np.arange(len(a)), next_token_ids].mean())
    cross = float(-(np.exp(a) * b).sum(axis=-1).mean())
    if not np.isfinite(cross) or cross <= 0:
        raise DetectionError(Code.INVALID_INPUT, "Degenerate reference cross-entropy.")
    return nll / cross, nll, cross


def weights_manifest(path: Path) -> str:
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise DetectionError(Code.MODEL, "Supply an existing local model directory.")
    inventory = {}
    for entry in sorted(root.rglob("*")):
        if not entry.is_file():
            continue
        if entry.is_symlink() and not entry.resolve().is_relative_to(root):
            raise DetectionError(Code.MODEL, "Materialize model files locally; external symlinks are not admitted.")
        if entry.suffix in (".pkl", ".pickle", ".pt", ".bin", ".py"):
            raise DetectionError(Code.MODEL, "Only local data-only safetensors model artifacts are admitted.")
        import hashlib
        hasher = hashlib.sha256()
        with entry.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
        inventory[str(entry.relative_to(root))] = hasher.hexdigest()
    if not any(name.endswith(".safetensors") for name in inventory):
        raise DetectionError(Code.MODEL, "No safetensors weights found.")
    return digest(canonical(inventory))


def local_reference_score(request: ReferenceRequest) -> ContrastiveResult:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        from loguru import logger
        logger.warning("optional_research_dependencies_missing")
        raise DetectionError(Code.BLOCKED, "Install the research extra and provide pinned local model weights.") from exc
    roots = [Path(request.model_a).expanduser().resolve(), Path(request.model_b).expanduser().resolve()]
    pins = [request.model_a_manifest_sha256, request.model_b_manifest_sha256]
    if [weights_manifest(root) for root in roots] != pins:
        raise DetectionError(Code.INTEGRITY, "Local reference model manifest pin mismatch.")
    tokenizers = [AutoTokenizer.from_pretrained(str(root), local_files_only=True,
                                               trust_remote_code=False) for root in roots]
    if (tokenizers[0].get_vocab() != tokenizers[1].get_vocab()
            or tokenizers[0].special_tokens_map != tokenizers[1].special_tokens_map):
        raise DetectionError(Code.MODEL, "Reference models must share token IDs and special-token semantics.")
    encoded = tokenizers[0](request.source, return_tensors="pt", truncation=False)
    second = tokenizers[1](request.source, return_tensors="pt", truncation=False)
    if not torch.equal(encoded["input_ids"], second["input_ids"]):
        raise DetectionError(Code.MODEL, "Reference tokenizers disagree on this input.")
    count = encoded["input_ids"].shape[1]
    if count < 2 or count > request.max_tokens:
        raise DetectionError(Code.LIMIT, "Input exceeds complete-input scoring coverage; no silent truncation.")
    if request.device == "cuda" and not torch.cuda.is_available():
        raise DetectionError(Code.BLOCKED, "CUDA was requested but is unavailable.")
    target = encoded["input_ids"][0, 1:].cpu().numpy()
    device_inputs = {key: value.to(request.device) for key, value in encoded.items()}
    logits = []
    for root in roots:
        model = AutoModelForCausalLM.from_pretrained(str(root), local_files_only=True,
                    trust_remote_code=False, use_safetensors=True).to(request.device).eval()
        with torch.inference_mode():
            result = model(**device_inputs).logits[0, :-1, :].float().cpu().numpy()
        logits.append(result)
        del model
        if request.device == "cuda":
            torch.cuda.empty_cache()
    score, nll, cross = contrastive_math(logits[0], logits[1], target)
    return ContrastiveResult(source_sha256=text_digest(request.source),
                model_a_manifest_sha256=pins[0], model_b_manifest_sha256=pins[1],
                score=score, nll_a=nll, cross_entropy_a_b=cross, scored_tokens=count - 1)
