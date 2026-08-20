# CAPTCHA And Bot-Detection Test Targets

Date: 2026-08-20

Research path: `brave-search` web queries for local CAPTCHA demos, bot-detection
repos, reCAPTCHA/hCaptcha test demos, FCaptcha, and synthetic CAPTCHA
benchmarks.

## Selected Defensive Eval Targets

- `WebDecoy/FCaptcha`
  - URL: https://github.com/WebDecoy/FCaptcha
  - Pinned commit used by `scripts/fcaptcha_reference_eval.py`:
    `dbe52eab975bb39161dd2a54d69924de51f63000`
  - Why selected: real open-source CAPTCHA/bot-detection project with local
    detection and input-forensics tests. No public provider, solver service,
    credentials, proxy, or bypass flow is required.

- `rebrowser/rebrowser-bot-detector`
  - URL: https://github.com/rebrowser/rebrowser-bot-detector
  - Pinned commit used by Surf live CDP eval:
    `e1a25b1ff264cc9a5b5ea7fe8a6dfc26e3b1c718`
  - Why selected: real browser bot-detection page that can be served on
    loopback and exercised through Surf CDP geometry, hit-test, and pointer
    dispatch receipts.

## Useful But Not Automated Here

- `librecaptcha/lc-core`
  - URL: https://github.com/librecaptcha/lc-core
  - Why: local Docker demo for CAPTCHA generation. Useful future fixture when
    the skill needs a self-hosted challenge page; not required for the current
    Surf/CDP pointer receipt proof.

- `prosopo/captcha`
  - URL: https://github.com/prosopo/captcha
  - Why: open-source CAPTCHA alternative. Useful candidate for a later
    provider-style local integration test.

## Excluded From Skill Runtime

- Public reCAPTCHA/hCaptcha demo pages and public provider test keys.
  - Reason: they contact third-party CAPTCHA providers and can blur the line
    between defensive evaluation and automated solving.

- Solver, stealth, bypass, or CAPTCHA-service SDK repos.
  - Examples found in search results included SeleniumBase CDP bypass examples,
    undetected browser drivers, and CAPTCHA-service demos.
  - Reason: these may be useful as adversarial reading for hardening, but they
    must not become runtime dependencies or automated eval paths for `captcha`
    or `surf`.
