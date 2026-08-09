# Dogpile Context7 Lane Proof

Generated from a fresh worktree at `origin/main` on 2026-08-09.

## Scope

This evidence covers the optional Dogpile Context7 lane added for code/API/library documentation questions.

- `mocked`: no
- `live`: no
- Proof class: deterministic static, unit, contract, and default-doctor evidence.
- This does not prove live Context7 API validity, account quota, semantic documentation relevance, live provider health, Hack scan execution, Battle runtime proof, or Memory durability.

## Commands

```bash
uv run --project skills/dogpile pytest \
  skills/dogpile/tests/test_security_research_packet.py \
  skills/dogpile/tests/test_source_bearing_evidence.py

./skills/dogpile/run.sh feature-eval \
  --out-dir skills/dogpile/local/context7-lane-20260809T085223-0400/feature-eval

./skills/dogpile/run.sh doctor \
  --out-dir skills/dogpile/local/context7-lane-20260809T085223-0400/doctor

./skills/dogpile/sanity.sh --quick

python3 scripts/check_mock_evidence_claims.py
```

## Results

- Pytest: `12 passed`.
- Feature eval: `status=passed`, `passed=26`, `failed=0`.
- Default doctor: `status=passed_with_skips`, `passed=14`, `skipped=14`, `failed=0`.
- Quick sanity: `Result: PASS (quick)`.
- Mock/proof claim guard: `OK: checked 575 test file(s); no mock+proof claim violations`.

## Context7 Receipt Findings

- Feature eval case `context7_library_docs_opt_in` passed and states that Context7 is wired as an opt-in library/API documentation lane for code-related questions.
- Doctor references the Context7 API docs:
  - `https://context7.com/api/v2/libs/search`
  - `https://context7.com/api/v2/context`
- Doctor saw `CONTEXT7_API_KEY` in the current process and interactive zsh environment.
- Default doctor classified Context7 as a credentialed API resource.
- Default doctor did not spend a Context7 API call: `context7_api_probe` is `skipped_not_requested`.

## Artifacts

- `source-audit.log`
- `search-help.txt`
- `pytest.log`
- `feature-eval.log`
- `feature-eval/receipt.json`
- `doctor.log`
- `doctor/receipt.json`
- `sanity-quick.log`
- `mock-claim-guard.log`
- `receipt-summary.json`
