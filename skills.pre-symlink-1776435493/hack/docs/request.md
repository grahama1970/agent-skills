# Code Review Request: Hack Skill & Dynamic Learning

Please perform a **brutal** code review of the new `hack` skill.

## Focus Areas

1.  **Code Quality**: Review `hack.py`, `run.sh`, `sanity.sh`, and `install_tools.sh` for robustness, error handling, and pythonic best practices (`typer`, `rich`).
2.  **Dynamic Learning Strategy**: Critique the approach defined in `docs/02_RESEARCH.md` and its implementation in `hack.py` (`learn` command).
    - Is the "Filesystem Handoff" with Readarr robust?
    - Is the `learn` command structure extensible for Exploit-DB/PacketStorm?
3.  **Security**: Ensure the tools are safe to run (e.g., input validation on `scan` targets).

## Files to Review

- `.pi/skills/hack/hack.py`
- `.pi/skills/hack/run.sh`
- `.pi/skills/hack/sanity.sh`
- `.pi/skills/hack/install_tools.sh`
- `.pi/skills/hack/docs/02_RESEARCH.md`
- `.pi/skills/hack/pyproject.toml`
