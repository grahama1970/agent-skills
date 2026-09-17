# Research and implementation map

Checked against primary research sources on **2026-09-17**. This is a targeted
engineering review, not an exhaustive systematic review or claim that every 2026
paper was reproduced. Abstracts and relevant HTML sections were reviewed. No paper
PDFs, restricted datasets, model weights or third-party code are redistributed.

The decisive design constraint is distribution shift: a score that separates one
collection is not evidence of reliable unknown-provider detection in an assessment.
AICD Bench spans roughly two million examples, 77 models and nine languages, and
reports serious limits for shifted, hybrid and adversarial cases. [AICD](https://arxiv.org/abs/2602.02079).

The UCSC multi-view system reports macro-F1 0.993 on validation and 0.845 on its
unseen-domain/language test. That gap motivates independent holdouts here; it is
not this project's measured accuracy. The paper's UniXcoder training and consistency
losses are **not** reproduced by our lightweight hashing/logistic baseline.
[UCSC-NLP](https://arxiv.org/abs/2604.26990).

## AICD Bench: A Challenging Benchmark for AI-Generated Code Detection

2026-02-02 · https://arxiv.org/abs/2602.02079

**Design use:** Hold-out family, domain and hybrid-label evaluation requirements.

**Delivered status:** Protocol implemented; original benchmark not downloaded or reproduced.

## UCSC-NLP at SemEval-2026 Task 13: Multi-View Generalization and Diagnostic Analysis of Machine-Generated Code Detection

2026-04-28 · https://arxiv.org/abs/2604.26990

**Design use:** Separate raw and normalized/structural code views; quantify distribution shift.

**Delivered status:** Handcrafted multi-view baseline only; no UniXcoder fine-tuning or paper reproduction.

## CodeMirage: A Multi-Lingual Benchmark for Detecting AI-Generated and Paraphrased Source Code from Production-Level LLMs

2025-05-27 · https://arxiv.org/abs/2506.11059

**Design use:** Include rewritten, unfamiliar-generator and language-shift conditions.

**Delivered status:** Evaluation design reference; multilingual detector/data collection remain unqualified.

## Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text

2024-10-13 (v3) · https://arxiv.org/abs/2401.12070

**Design use:** Two-reference-model contrastive likelihood rather than free-text authorship judgments.

**Delivered status:** Local-only adapter and tested numerical kernel; real model weights and code-specific operating threshold unqualified.

## DualCodeDetect: Zero-Shot LLM-Generated Code Detection via Dual-Channel Perturbation

2026 (FSE research track) · https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/112/DualCodeDetect-Zero-Shot-LLM-Generated-Code-Detection-via-Dual-Channel-Perturbation

**Design use:** Candidate secondary code-aware perturbation score.

**Delivered status:** Researched, not implemented. No heuristic transform is falsely certified semantics-preserving.

## MATRIX: Multi-Layer Code Watermarking via Dual-Channel Constrained Parity-Check Encoding

2026-04-17 · https://arxiv.org/abs/2604.16001

**Design use:** Optional explicit provenance for deliberately marked outputs.

**Delivered status:** Researched only; not a detector for arbitrary unmarked provider outputs.

## Multi-Channel Spread-Spectrum Code Watermarking

2026-07-07 · https://arxiv.org/abs/2607.06009

**Design use:** Robustness and coverage considerations for an optional watermark adapter.

**Delivered status:** Researched only; no embedded watermark decoder or universal fingerprint claimed.

## MultiAIGCD: a comprehensive dataset for AI generated code detection covering multiple languages, models, prompts, and scenarios

2026 (journal version) · https://link.springer.com/article/10.1007/s00521-026-12336-0

**Design use:** Consider multiple prompting and editing scenarios rather than only clean generation.

**Delivered status:** Dataset shortlist; license and provenance admission still required.

## Algorithmic follow-through

The delivered baseline uses two code views plus structural scalars and an explicitly
trained classifier. It is a tractable baseline that can be replaced under a versioned
feature/model contract, not a renamed state-of-the-art neural system.

The optional likelihood adapter computes an explicit NLL(A)/CE(A,B) ratio. Its
causal alignment, token compatibility, complete-input budget and safe local loading
are part of the implementation. Actual Transformer inference is unexecuted without
trusted local weights. A natural-language Binoculars threshold is not transplanted
to code; the original paper's text results do not become code-detection evidence.

DualCodeDetect is retained as a next experiment, not represented by ad hoc renaming
or transformations whose semantics were never established. Watermarking work is
relevant only when a supported mark was actually embedded; lack of a mark is not
proof of human authorship. Model provenance, similarity and candidate understanding
remain distinct evidence types.

No general-purpose LLM judge is allowed to invent an authorship probability from
comments, naming style or intuition. Future explanatory models may summarize only
observed signals and limitations; they cannot replace the deterministic gates.
