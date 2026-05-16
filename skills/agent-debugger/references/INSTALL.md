# Agent Debugger Install Notes

## Skill

From the repository root that contains `skills/agent-debugger`:

```bash
python3 -m pip install typer==0.12.5
bash skills/agent-debugger/sanity.sh
```

Generate a Python debug session from a target project root:

```bash
skills/agent-debugger/run.sh init-python \
  --task qra-null-key \
  --target scripts/rebuild_qra.py \
  --target-args-json '["--control", "AC-1"]' \
  --breakpoint src/sparta/qra_loader.py:402:control_id,bind_vars,query_text,result
```

Use `--breakpoints-json '["file.py:10:x", "file.py:20:y"]'` for multiple breakpoints.

This creates `.plan-iterate/<task>/debug/` artifacts and updates `.vscode/launch.json`.

## VS Code Bridge Extension

The generated Python launch config uses VS Code's `debugpy` debug type, so the target VS Code workspace needs the Python debugger support that provides `debugpy` launch handling.

Open the extension folder:

```bash
cd vscode-extensions/agent-debugger-bridge
npm install
npm run compile
```

Run in development:

1. Open `vscode-extensions/agent-debugger-bridge` in VS Code.
2. Press `F5` to open an Extension Development Host.
3. Open the target project in that Extension Development Host.
4. Run `Agent Debugger: Load Manifest`.
5. Run `Agent Debugger: Run Current Manifest`.

Package locally:

```bash
npm run package
code --install-extension agent-debugger-bridge-0.1.0.vsix
```

## Debugging Flow

1. Agent creates the manifest and launch config.
2. Human opens VS Code on the target project.
3. Bridge loads the latest `.plan-iterate/**/debug/debug_manifest.json`.
4. Bridge sets agent-requested breakpoints.
5. Bridge starts the named launch config.
6. On each stop, bridge writes observations to `debug_observations.jsonl`.
7. Human and agent discuss runtime state before patching.

## v1 Limits

- Python targets only.
- No attach mode.
- No native data breakpoints.
- No reverse debugging.
- Replay means stop and restart the same managed launch config.
