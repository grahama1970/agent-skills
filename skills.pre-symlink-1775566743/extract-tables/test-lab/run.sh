#!/usr/bin/env bash
set -euo pipefail

TEST_LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$TEST_LAB_DIR")"
BLIND_DIR="$TEST_LAB_DIR/blind_tests"

case "${1:-}" in
    verify-task)
        TASK_ID="${2:-}"
        TARGET="${3:-$SKILL_DIR}"
        shift 3 2>/dev/null || true

        if [[ -z "$TASK_ID" ]]; then
            echo "FAIL: No task ID provided"
            exit 1
        fi

        TEST_FILE="$BLIND_DIR/test_task_${TASK_ID}.py"
        if [[ ! -f "$TEST_FILE" ]]; then
            echo "WARN: No blind test for task $TASK_ID (not yet generated)"
            exit 0
        fi

        echo "Running blind test for Task $TASK_ID..."
        cd "$SKILL_DIR"
        PYTHONPATH="$SKILL_DIR/src/python:$SKILL_DIR:${PYTHONPATH:-}" \
            python -m pytest "$TEST_FILE" -v --tb=short 2>&1 | \
            grep -E "^(PASSED|FAILED|ERROR|test_|.*::.*)" || true

        # Get actual exit code
        PYTHONPATH="$SKILL_DIR/src/python:$SKILL_DIR:${PYTHONPATH:-}" \
            python -m pytest "$TEST_FILE" --tb=no -q > /dev/null 2>&1
        EXIT=$?

        if [[ $EXIT -eq 0 ]]; then
            echo "PASS: Task $TASK_ID blind test passed"
        else
            echo "FAIL: Task $TASK_ID blind test failed"
        fi
        exit $EXIT
        ;;

    verify-all)
        DOMAIN="${2:-extract-tables}"
        PASS=0
        FAIL=0
        SKIP=0

        for test_file in "$BLIND_DIR"/test_task_*.py; do
            [[ -f "$test_file" ]] || continue
            TASK=$(basename "$test_file" .py | sed 's/test_task_//')

            cd "$SKILL_DIR"
            if PYTHONPATH="$SKILL_DIR/src/python:$SKILL_DIR:${PYTHONPATH:-}" \
                python -m pytest "$test_file" --tb=no -q > /dev/null 2>&1; then
                echo "PASS: Task $TASK"
                PASS=$((PASS + 1))
            else
                echo "FAIL: Task $TASK"
                FAIL=$((FAIL + 1))
            fi
        done

        echo ""
        echo "Results: $PASS passed, $FAIL failed, $SKIP skipped"
        [[ $FAIL -eq 0 ]]
        ;;

    list)
        echo "Blind tests for extract-tables:"
        for test_file in "$BLIND_DIR"/test_task_*.py; do
            [[ -f "$test_file" ]] || { echo "  (none generated yet)"; exit 0; }
            TASK=$(basename "$test_file" .py | sed 's/test_task_//')
            echo "  Task $TASK: $test_file"
        done
        ;;

    *)
        echo "Usage: run.sh {verify-task|verify-all|list} [args...]"
        exit 1
        ;;
esac
