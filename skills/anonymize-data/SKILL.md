---
name: anonymize-data
description: >
  Anonymize supported CSV, JSON, UTF-8 text, and SQLite files using an explicit
  policy through the oai-trial project. Use for anonymize data, pseudonymize
  exports, redact policy literals, or discover and explicitly approve fuzzy
  name aliases. The skill is a thin CLI/Docker interface, not another engine.
disable-model-invocation: true
project-path: ${HOME}/workspace/experiments/oai-trial
triggers:
  - anonymize data
  - anonymize this file
  - pseudonymize customer exports
  - redact policy literals
  - discover fuzzy name aliases
provides:
  - data-anonymization
  - name-alias-discovery
composes:
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
runtime_self_improvement: basic
taxonomy:
  - precision
  - resilience
  - privacy
disciplines:
  - data-engineering
  - compliance-security
---

# Anonymize data

Operate the canonical `oai-trial` project. Do not duplicate its matcher,
format adapters, verifier, schemas or error handling in this skill. The
project's existing argparse CLI is intentionally retained; this wrapper adds
no Python CLI or service.

## Setup and main operation

`ANONYMIZE_DATA_ROOT` overrides the default primary checkout above. Setup needs
`uv` and installs the project's declared development/discovery extras. Runtime
operations need no Memory, provider credentials, LLM, network or database service.

```bash
./run.sh setup
./run.sh --input /data/exports --policy /data/policy.json --output /data/release
./run.sh anonymize --input /data/export.sqlite --policy /data/policy.json --output /data/release
```

Input is one `.csv`, `.json`, `.txt` or `.sqlite` file, or a directory of those
files. Policy must be a separate regular file. Use a dedicated **empty** output
directory outside the inputs. Originals are copied into a private temporary
snapshot; successful output contains only `corpus/` and `report.json`.

The existing bundle interface remains available:

```bash
./run.sh run --input /data/bundle --output /data/release
./run.sh verify --input /data/bundle --output /data/release
./run.sh inspect /data/release
```

A bundle contains `policy.json` and `corpus/`. The policy, canonical identity,
protected-value rules, typed failures and report schema are owned by the project.
Read its `README.md`, `docs/ANONYMIZATION_SEMANTICS.md` and `schemas/report.schema.json`
when interpreting them. Do not declare success from an exit code alone: read the
actual report, validate its readiness fields, and inspect output for the requested
format. Corrupt or missing reports are not READY.

## Optional RapidFuzz discovery: never automatic replacement

```bash
./run.sh discover --input /data/exports --policy /data/policy.json --output /data/work/review.json
./run.sh approve-discovery --input /data/exports --policy /data/policy.json \
  --review /data/work/review.json --approve CANDIDATE_ID --output /data/work/approved-policy.json
./run.sh --input /data/exports --policy /data/work/approved-policy.json --output /data/release
```

Discovery compares whole structured string values and whole text lines against
policy entries of type `name`. It is not NLP span extraction or a general PII
scanner. Defaults: similarity threshold 90, separation margin 5; configurable
with `--threshold` and `--margin`. Ties, near ties, protected values, values
containing digits or identifier punctuation such as `@`, `/`, `_`, and
already-known literals are not proposed. Apostrophes, hyphens and periods are
allowed in name-shaped text; similarity is never proof that two people are one.

**Ask the operator to approve specific candidate IDs.** Never approve from the
similarity score alone. Approval re-derives the proposals against the current
policy/corpus, rejects stale/edited reviews, and compiles an exact-match policy.
Unapproved proposals never affect anonymization. `release_ready: false` is
mandatory on discovery/approval receipts.

Review and approved-policy files contain raw names: keep them outside releases,
logs and shared reports. They are created mode 0600 and never overwrite an
existing file. Temporary snapshots default to the artifact drive; override with
`ANONYMIZE_DATA_WORK_DIR` when needed.

## Docker remains the standalone interface

From the project checkout:

```bash
docker build -t anonymization-trial .
docker run --rm anonymization-trial
# Optional discovery-enabled image; default image keeps the exact engine dependency-free.
docker build --build-arg INCLUDE_DISCOVERY=1 -t anonymization-trial:discovery .
```

Mount only the requested input/policy read-only and a dedicated output directory.
The same project CLI runs inside the image; the evaluator does not need this skill.
See the project's `docs/DISCOVERY.md` for complete mounted command examples.

## Failure and proof boundary

The wrapper preserves project exit codes and sanitized error codes. Missing
project/setup and wrong installed-package paths fail before processing. Use
`--help` for the actual argument contract. Discovery is review material, not a
release, anonymity guarantee, confidence probability, or human authorization.

`./sanity.sh` runs real positive, negative and adversarial CLI checks. The retained
`fixtures/agentic_eval.json` repeats them and requires artifact readback. Prior
trial qualification does not automatically qualify these post-trial extensions.

## Representation rule (operator 2026-09-11)

PII must be matched against the **value**, not the string: before any
JSON/SQL scalar is passed through unchanged, stringify it canonically
(phone-shaped numbers in E.164 form) and run the policy match on the
stringified form. Fixtures must include every PII class in every JSON
scalar type. A phone number stored as an integer is the same phone
number. See $best-practices-skills "Value representation matrix".

## Hardening lessons (do not relearn these the hard way)

The trial was disqualified because a phone stored as a JSON/SQLite integer
passed the string-only matcher. The root cause was a process error: the
acceptance check was authored from what the code did, not derived from the
delivered spec. These rules exist so that class of miss cannot recur.

1. **Derive the check from the spec, not the code.** `policy.json` lists the
   exact sensitive values. The correct acceptance check is "none of those
   values appears in the decoded output, in any representation" — read the
   values from the policy file, never a hand-authored list. Prove the check
   depends on the spec with a dependency probe (flip a policy value → the
   result must flip). Reference implementation: the project's
   `scripts/spec_derived_check.py` wired into `scripts/verify.sh`.

2. **The independent verifier must share no assumption with the transform.**
   The original verifier had the same string-only blind spot as the producer,
   so nothing failed closed. The verification oracle must be
   representation-aware and independent: parse JSON (decode `\uXXXX`), expand
   numeric scalars to integer/decimal forms, NFC/NFD-normalize both sides,
   scan SQLite table+view cells AND `sqlite_master` DDL AND every header
   integer, and scan the whole released boundary including `report.json` — not
   just `corpus/`.

3. **The full representation class is a checklist, not a single bug.** Each of
   these can carry a sensitive value past a naive matcher; the project fixes
   and retains a guard for every one: typed numeric scalars (int/float,
   scientific notation), SQLite BLOB (fail-closed), Unicode NFC/NFD, view
   reconstruction, freelist residue, hostile-DB schema (expression/partial
   indexes, non-deterministic views, computed DEFAULTs), schema-DDL literals,
   and persistent header integers. See the project's
   `docs/SECURITY_REMEDIATION.md` for the full table.

4. **Prove it through the real Docker path, deterministically.** Verification
   must be a committed script that builds the image, runs the brief's exact
   commands, and reads back the released bytes with hard PASS/FAIL exits — not
   agent prose. Reference: `security/docker_brief_contract.py` (build + both
   brief commands + representation-aware leak scan + input precondition) and
   `security/docker_hardening_matrix.py` (adversarial holes through
   `docker run`). Record the git commit and built image id.

5. **Scope honestly.** Deterministic public-namespace pseudonyms disclose
   equality/frequency and offer no external-linkage resistance; the run report
   states this in `key_mode` and `does_not_establish`. A policy value equal to
   a mandatory SQLite format constant is a degenerate input, not real PII; the
   pipeline fails closed on it and that residue is documented as scoped.
