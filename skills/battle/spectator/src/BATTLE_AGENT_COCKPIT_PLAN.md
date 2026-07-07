# Battle Agent Detail Cockpit Recovery Plan

## Status

This is a right-pane-only recovery patch.

The accepted product direction is the Battle-004 core mockup. The shell is immutable. The only allowed visual delta is inside the existing right-side `AGENT DETAIL` pane.

## Immutable shell

Do not edit or restyle:

- Header / campaign area
- Score block
- Live events block
- Blue Team Control Strip
- Left spectator rail
- Center race graph
- Footer / bottom controls
- Dark acrylic / neon race-board shell style
- Overall layout proportions
- Right pane outer slot dimensions and placement

## Editable region

Only this file may implement the cockpit UI:

```text
AgentDetailPane.tsx
```

The pane may change internally, but it must remain the shell's `AGENT DETAIL` region.

## Product rule

Spectators care about the selected exploit first.

Therefore:

- Primary display name: selected exploit name
- Muted diagnostic metadata: Tau run id / subagent id
- Tau is internal machinery
- The pane is a cockpit for the selected exploit's Tau subagent run

## Data/proof rule

The pane may render only emitted public data:

- emitted turn events
- emitted stdout/stderr excerpts
- emitted Tau skill/tool events
- emitted receipt references
- selected exploit metadata
- selected payload metadata
- Tau/subagent run metadata

The pane must not render:

- hidden chain-of-thought
- invented live proof
- fake receipts
- fake skill events
- fake memory/project-knowledge events
- synthetic logs presented as real logs

## Final allowed changed files

Only these files may remain changed:

```text
packages/ux-lab/src/components/battle/dual-agent/AgentDetailPane.tsx
packages/ux-lab/src/components/battle/dual-agent/BATTLE_AGENT_COCKPIT_PLAN.md
```

## Mandatory diff gate

```bash
cd /home/graham/workspace/experiments/pi-mono

BAD_FILES="$(git diff --name-only \
  | grep -Ev '^packages/ux-lab/src/components/battle/dual-agent/AgentDetailPane.tsx$|^packages/ux-lab/src/components/battle/dual-agent/BATTLE_AGENT_COCKPIT_PLAN.md$' || true)"

if [ -n "$BAD_FILES" ]; then
  echo "FAIL: shell/global drift remains:"
  echo "$BAD_FILES"
  exit 1
fi

echo "PASS: final diff scope is locked to AgentDetailPane.tsx and plan doc."
```

## Mandatory build gate

```bash
cd /home/graham/workspace/experiments/pi-mono/packages/ux-lab
npm run build
```

Existing unrelated warnings are not part of this task. New Battle errors or warnings fail the task.

## Mandatory visual gate

The final screenshot must prove:

- Header/campaign area unchanged
- Score/live events unchanged
- Blue Team Control Strip unchanged
- Left rail unchanged
- Center graph unchanged
- Footer controls unchanged
- Right pane outer slot unchanged
- Only the internals of `AGENT DETAIL` changed

If the screenshot shows drift outside the right pane, the task fails even if the build passes.
