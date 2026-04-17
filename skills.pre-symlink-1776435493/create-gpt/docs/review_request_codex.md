# Review create-gpt teacher-student pipeline and 3-tier router

## Repository and branch

- **Repo:** `grahama1970/pi-mono`
- **Branch:** `feat-triggers`
- **Paths of interest:**
  - `.pi/skills/create-gpt/scripts/teacher.py`
  - `.pi/skills/create-gpt/scripts/router.py`
  - `.pi/skills/create-gpt/scripts/teacher_student_loop.py`
  - `.pi/skills/create-gpt/scripts/confidence_router.py`
  - `.pi/skills/create-gpt/task_spec.py`
  - `.pi/skills/create-gpt/run.sh`

## Summary

New teacher-student training pipeline and 3-tier inference router for create-gpt skill. Teacher generates labeled data via scillm, student trains via SFT/GRPO, router cascades through heuristic/local-GPT/scillm tiers with SHA1 caching and metrics.

## Objectives

### 1. (Specify objectives)

(Specify objectives)

## Constraints for the patch

- **Output format:** Unified diff only, inline inside a single fenced code block.
- Include a one-line commit subject on the first line of the patch.
- Hunk headers must be numeric only (`@@ -old,+new @@`); no symbolic headers.
- Patch must apply cleanly on branch `feat-triggers`.
- No destructive defaults; retain existing behavior unless explicitly required by this change.
- No extra commentary, hosted links, or PR creation in the output.

## Acceptance criteria

- (Specify acceptance criteria)

## Test plan

**Before change** (optional): (Describe how to reproduce the issue)

**After change:**

1. (Specify test steps)

## Implementation notes

## Auto-Gathered Context

## README.md
<p align="center">
  <a href="https://shittycodingagent.ai">
    <img src="https://shittycodingagent.ai/logo.svg" alt="pi logo" width="128">
  </a>
</p>
<p align="center">
  <a href="https://discord.com/invite/3cU7Bz4UPx"><img alt="Discord" src="https://img.shields.io/badge/discord-community-5865F2?style=flat-square&logo=discord&logoColor=white" /></a>
  <a href="https://github.com/badlogic/pi-mono/actions/workflows/ci.yml"><img alt="Build status" src="https://img.shields.io/github/actions/workflow/status/badlogic/pi-mono/ci.yml?style=flat-square&branch=main" /></a>
</p>
<p align="center">
  <a href="https://pi.dev">pi.dev</a> domain graciously donated by
  <br /><br />
  <a href="https://exe.dev"><img src="packages/coding-agent/docs/images/exy.png" alt="Exy mascot" width="48" /><br />exe.dev</a>
</p>

# Pi Monorepo

> **Looking for the pi coding agent?** See **[packages/coding-agent](packages/coding-agent)** for installation and usage.

Tools for building AI agents and managing LLM de

(Add implementation hints here)

## Known touch points

- (List files/functions to modify)

## Clarifying questions

*Answer inline here or authorize assumptions:*

1. (Add any clarifying questions here)

## Deliverable

- Reply with a single fenced code block containing a unified diff that meets the constraints above (no prose before/after the fence)
- In the chat, provide answers to each clarifying question explicitly so reviewers do not need to guess
- Do not mark the request complete if either piece is missing; the review will be considered incomplete without both the diff block and the clarifying-answers section
