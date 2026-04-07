# KDE/QML Skill-App code review and patch

## Repository and branch

- **Repo:** `/home/graham/workspace/experiments/pi-mono`
- **Branch:** (current working tree)
- **Paths of interest:**
  - `bridge.py`
  - `app.py`
  - `qml/*.qml` (all QML UI files)
  - `qml/tab-registry.json`

## Context

This is a PySide6 + QML desktop application following the Skill-App Pattern:
- PySide6 Python bridge wrapping a CLI via subprocess (never imports internals)
- QML UI with EmbryStyle singleton (NVIS MIL-STD-3009 dark theme)
- Tab-based navigation with tab-registry.json
- KDE-style architecture with QObject properties, signals, slots

## Review focus

1. **Bridge correctness**: Subprocess safety, thread safety, signal emission from threads.
2. **QML best practices**: Property ordering (id→properties→sizing→anchors→visual→behaviors→children). Accessible.name on all interactive elements.
3. **NVIS compliance**: All colors from EmbryStyle singleton, no hardcoded colors.
4. **Memory safety**: Null guards, `clip: true` on ListViews, model data validation.
5. **Security**: No command injection in subprocess calls, no path traversal.
6. **Architecture**: Clean separation between bridge and UI, consistent patterns.

## Objectives

- Provide a unified diff that addresses issues found in the focus areas above.
- Keep changes scoped to the listed files.
- Respect the skill-app pattern and KDE/QML best practices.

## Constraints for the patch

- **Output format:** Unified diff only, in a single fenced code block.
- Keep behavior changes minimal and well-justified.
- No new dependencies.
- Preserve CLI subprocess boundary (no importing CLI internals).
- Use EmbryStyle/EmbryStyle singleton for all colors/sizing/durations.
- Do not remove any apparent intentional functionality; if necessary, add guards instead.

## Clarifying questions

Ask questions only if required to choose between valid implementation options.
