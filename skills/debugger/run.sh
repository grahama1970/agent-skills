#!/usr/bin/env bash
# /debugger front door — one line to drive the debugger from any skill, agent, or human.
#
# Usage:
#   ./run.sh break <file:line> [--local NAME ...] -- <python-cmd ...>   headless breakpoint proof
#   ./run.sh stop <file:line> [--local NAME ...] [--expand NAME[:D]]    live VS Code bridge stop
#   ./run.sh walkthrough <spec.json> [--speak] [--voice] [--commands S] narrated breakpoint tour
#   ./run.sh session [--wait-seconds N]                                 collaborative live session
#   ./run.sh validate <proof.json> [--expect-valid|--expect-invalid] [--repo-root P]
#   ./run.sh matrix [--suite NAME ...]                                  capability-gated eval matrix
#   ./run.sh spec-from-proof <proof.json> --out spec.json          session -> walkthrough spec
#   ./run.sh recall <query>                                             recall stored debugger lessons
#   ./run.sh verify                                                     fast self-check + receipt
#
# All subcommands own the env plumbing (uv project venv, workspace detection,
# extension-host kind), so a caller never exports UV_PROJECT_ENVIRONMENT or
# assembles `uv run` incantations. Live subcommands need an open, trusted
# VS Code workspace (DEBUGGER_VSCODE_WORKSPACE, default: the git toplevel of
# $PWD) with the debugger-vscode-bridge extension; they fail closed with
# BRIDGE_BLOCKED otherwise.
set -euo pipefail
unset VIRTUAL_ENV 2>/dev/null || true

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

py() { uv run --project "$SKILL_DIR" python "$@"; }

default_workspace() {
    if [ -n "${DEBUGGER_VSCODE_WORKSPACE:-}" ]; then
        echo "$DEBUGGER_VSCODE_WORKSPACE"
    else
        git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || echo "$PWD"
    fi
}

usage() { sed -n '3,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

cmd="${1:-help}"
case "$cmd" in
    break)
        shift
        [ "$#" -ge 1 ] || { echo "usage: ./run.sh break <file:line> [--local NAME ...] -- <python-cmd ...>" >&2; exit 2; }
        bp="$1"; shift
        exec_args=()
        while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do exec_args+=("$1"); shift; done
        [ "${1:-}" = "--" ] && shift
        [ "$#" -ge 1 ] || { echo "break requires the reproduction command after --" >&2; exit 2; }
        # The debuggee usually imports sibling modules from its own directory;
        # put the caller's cwd on PYTHONPATH so `./run.sh break` works from the
        # scenario directory with no env assembly.
        export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$PWD"
        py "$SKILL_DIR/scripts/capture_breakpoints.py" --break "$bp" "${exec_args[@]}" -- "$@"
        ;;
    stop)
        shift
        [ "$#" -ge 1 ] || { echo "usage: ./run.sh stop <file:line> [--local NAME ...] [--expand NAME[:D]] [--launch-config-name N]" >&2; exit 2; }
        bp="$1"; shift
        ws="$(default_workspace)"
        host_kind="${DEBUGGER_VSCODE_HOST_KIND:-ui}"
        out="$(py "$SKILL_DIR/scripts/request_vscode_bridge.py" \
            --workspace "$ws" --action restart --break "$bp" \
            --expect-extension-host-kind "$host_kind" \
            --launch-config-name "${DEBUGGER_LAUNCH_CONFIG:-Debugger walkthrough (\$debugger)}" \
            "$@" | tail -1)"
        echo "STATUS_PATH $out"
        # Poll to a terminal state so the caller gets a settled receipt.
        state=pending
        for _ in $(seq 1 "${DEBUGGER_STOP_POLLS:-75}"); do
            sleep 2
            state="$(py -c "import json,sys; print(json.load(open(sys.argv[1])).get('status'))" "$out" 2>/dev/null || echo pending)"
            case "$state" in stopped|stopped-not-proof|error|terminated) break;; esac
        done
        echo "STATUS $state"
        case "$state" in
            stopped|stopped-not-proof) exit 0 ;;
            *) echo "BRIDGE_BLOCKED live stop did not settle to a pause (status=$state); is the workspace open+trusted with the bridge extension?" >&2; exit 3 ;;
        esac
        ;;
    walkthrough)
        shift
        [ "$#" -ge 1 ] || { echo "usage: ./run.sh walkthrough <spec.json> [--speak] [--voice] [--commands S] [--transcript P]" >&2; exit 2; }
        spec="$1"; shift
        exec env DEBUGGER_VSCODE_WORKSPACE="$(default_workspace)" \
            uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/vscode_walkthrough.py" --spec "$spec" "$@"
        ;;
    session)
        shift
        exec env DEBUGGER_VSCODE_WORKSPACE="$(default_workspace)" \
            uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/vscode_bridge_session.py" "$@"
        ;;
    validate)
        shift
        exec uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/validate_debugger_proof.py" "$@"
        ;;
    matrix)
        shift
        exec env DEBUGGER_VSCODE_WORKSPACE="$(default_workspace)" \
            uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/run_eval_matrix.py" "$@"
        ;;
    recall)
        shift
        exec uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/recall_debugger_lessons.py" "$@"
        ;;
    spec-from-proof)
        shift
        # Turn a captured session (run.sh break proof) into a runnable
        # walkthrough spec: debug it, then explain what happened.
        exec uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/generate_walkthrough_spec.py" "$@"
        ;;
    verify)
        shift
        # Fast self-check: proof validator over the canonical fixtures + guard
        # primitives + ladder gate. Deterministic, no live bridge required.
        cd "$SKILL_DIR/fixtures"
        py "$SKILL_DIR/scripts/validate_debugger_proof.py" proofs/canonical-valid.json --expect-valid
        py "$SKILL_DIR/scripts/validate_debugger_proof.py" proofs/canonical-tampered-proofvalid.json --expect-invalid
        T="$(mktemp -d)"; mkdir -p "$T/root" "$T/outside"; ln -s "$T/outside" "$T/root/esc"
        if python3 "$SKILL_DIR/scripts/debugger_runtime_guard.py" check-containment "$T/root" "$T/root/esc/x" >/dev/null 2>&1; then
            echo "VERIFY-FAILED containment guard accepted a symlink escape" >&2; exit 1
        fi
        node "$SKILL_DIR/vscode-bridge/scripts/protocol-tests.mjs" >/dev/null
        echo "DEBUGGER-VERIFY-OK proof-validator + containment-guard + bridge-protocol-tests"
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "unknown subcommand: $cmd" >&2
        usage >&2
        exit 2
        ;;
esac
