# Agent Debugger Install Notes

## Skill dependencies

From the repository root that contains `skills/agent-debugger`:

```bash
python3 -m pip install typer==0.12.5 debugpy==1.8.16
bash skills/agent-debugger/sanity.sh
```

## Generate a Python debug session

From a target project root:

```bash
skills/agent-debugger/run.sh init-python \
  --task qra-null-key \
  --target scripts/rebuild_qra.py \
  --target-args-json '["--control", "AC-1"]' \
  --breakpoints-json '["src/sparta/qra_loader.py:402:control_id,bind_vars,query_text,result"]'
```

This creates `.plan-iterate/<task>/debug/` artifacts and updates `.vscode/launch.json`.

## Mode 1: agent-only headless debugpy/DAP

Run without VS Code:

```bash
skills/agent-debugger/run.sh run-headless \
  --manifest .plan-iterate/qra-null-key/debug/debug_manifest.json
```

The runner launches the generated harness through debugpy/DAP on `127.0.0.1`, sets the manifest breakpoints, evaluates requested expressions, and writes observations to `debug_observations.jsonl`.

## Mode 2: human-agent VS Code collaboration

The generated Python launch config uses VS Code's `debugpy` debug type, so the target VS Code workspace needs Python debugger support that provides `debugpy` launch handling.

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

1. Agent creates the harness, manifest, and launch config.
2. Agent runs headless mode, or human opens VS Code collaboration mode.
3. Runtime observations are written to `debug_observations.jsonl`.
4. Human and/or agent discuss runtime state before patching.

## v1 Limits

- Python targets only.
- No attach mode.
- No native data breakpoints.
- No reverse debugging.
- Headless debugpy binds to `127.0.0.1` only.
- VS Code replay means stop and restart the same managed launch config.
