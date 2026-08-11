# ReCAP integration contract

## Approved source

The runtime accepts one source identity, recorded in `upstream.json`:

- repository: `ASTRAL-Group/ReCAP-Agent`
- commit: `577c7728ed159756a6cb6cbd1a58897fe288f73e`
- provider: `dynamic`
- model family/parser: `qwen3`

The skill does not clone, pull, download weights, edit upstream files, or accept
a floating branch. A source update requires an intentional code review and pin
change.

## Reused upstream behavior

ReCAP's evaluation framework opens a synthetic challenge in Playwright, captures
screenshots, sends prompt and image to the local model endpoint, parses actions,
executes them, checks solved state, and writes a benchmark summary. The captcha
skill invokes that existing `captcha_eval_framework/main.py` entrypoint.

## Excluded upstream behavior

The following upstream surfaces are not reachable through this skill:

- `halligan` provider and real-world CAPTCHA samples;
- `complete` mode and its unbounded/large campaign shape;
- `openai-cua` and public model endpoints;
- arbitrary provider registration or custom action parsers;
- inherited proxy, cookie, credential, or browser-session inputs.

## Surf boundary

Surf is not substituted for ReCAP's Playwright executor. Before ReCAP starts,
`captcha` runs Surf's producer-owned `capabilities --json` command, validates the
`surf.capabilities.v1` contract, opens a fresh isolated Surf window on the exact
loopback challenge URL, observes the final URL and challenge identifier, captures
a PNG, and closes the created tab. The typed proof and screenshot are stored in
the run. ReCAP's model-driven benchmark interaction remains unchanged and owned
by its Playwright evaluator.

## Output interpretation

The only permitted positive claim is a count/rate derived from the validated
summary for the recorded synthetic run. Do not extrapolate to a named vendor,
public site, production defense, or generalized bypass capability.
