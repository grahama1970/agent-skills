---
name: create-styleguide
version: 1.0.0
description: >
  Per-surface visual styleguide lifecycle — capture, annotate with token callouts,
  audit via /review-design, track token debt, and detect visual drift between rounds.
  Composes /create-design-board and /review-design into a repeatable pipeline.
provides:
  - styleguide
  - visual-audit
  - token-debt-tracking
composes:
  - create-design-board
  - review-design
  - memory
triggers:
  - create styleguide
  - build styleguide
  - visual styleguide
allowed-tools:
  - Bash
  - Read
  - Write
taxonomy:
  - design
  - compliance
  - visual
disciplines:
  - ui-design-engineering
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /create-styleguide

Per-surface visual styleguide lifecycle for Embry OS's 10 UX surfaces.

## Commands

- `build` — Full pipeline: annotate -> audit -> debt -> assemble STYLEGUIDE.md
- `annotate` — Just the Pillow annotation step (token callouts on screenshots)
- `audit` — Run /review-design on a surface
- `diff` — Visual regression between rounds (pixel diff + block-SSIM)
- `status` — Show which surfaces have styleguides, debt counts, last audit dates
- `dry-run` — Generate sample output without LLM calls (used by sanity.sh)

## Usage

```bash
./run.sh build --surface S4 --skip-audit
./run.sh annotate --screenshots ./shots/ --tokens ./tokens.json --output ./annotated/
./run.sh diff --surface S4 --before ./round1/ --after ./round2/
./run.sh status
```
