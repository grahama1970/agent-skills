#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_PI_MONO="$(cd "$SKILL_DIR/../../.." && pwd)"
PI_MONO="$DEFAULT_PI_MONO"
if [[ -d "$DEFAULT_PI_MONO/.pi/skills" ]]; then
  SKILLS_DIR="$DEFAULT_PI_MONO/.pi/skills"
elif [[ -f "$SKILL_DIR/../memory/SKILL.md" ]]; then
  SKILLS_DIR="$(cd "$SKILL_DIR/.." && pwd)"
  if [[ -d "$HOME/workspace/experiments/pi-mono" ]]; then
    PI_MONO="$HOME/workspace/experiments/pi-mono"
  fi
else
  SKILLS_DIR="$DEFAULT_PI_MONO/.pi/skills"
fi
ARTIFACTS_DIR="$SKILL_DIR/artifacts"
INBOX_REGISTRY="${HOME}/.agent-inbox/projects.json"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$ARTIFACTS_DIR"

run_skill() { "$SKILLS_DIR/$1/run.sh" "${@:2}"; }

# Timeout-aware skill runner: wraps run_skill with per-step timeout
# Uses the `timeout` command to kill hung skills
STEP_TIMEOUT=300  # default 5 min per step

run_skill_timed() {
  timeout "$STEP_TIMEOUT" "$SKILLS_DIR/$1/run.sh" "${@:2}"
}

write_json_object_from_output() {
  local raw_file="$1"
  local output_file="$2"

  python3 - "$raw_file" "$output_file" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

raw_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
text = raw_path.read_text()
decoder = json.JSONDecoder()
payload = None

for index, char in enumerate(text):
    if char not in "{[":
        continue
    try:
        candidate, _ = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    payload = candidate
    break

if payload is None:
    raise SystemExit(1)

output_path.write_text(json.dumps(payload, indent=2) + "\n")
PY
}

# Read timeout from .monitor-codebase.json (default: 3600s = 1hr total)
get_project_timeout() {
  local project_path="$1"
  local config_file="$project_path/.monitor-codebase.json"
  if [[ -f "$config_file" ]]; then
    python3 -c "import json; print(json.load(open('$config_file')).get('timeout', 3600))" 2>/dev/null || echo 3600
  else
    echo 3600
  fi
}

resolve_project_path() {
  local project="$1"
  if [[ -d "$project" ]]; then echo "$project"; return; fi
  if [[ -f "$INBOX_REGISTRY" ]]; then
    local path
    path=$(python3 -c "import json,sys; d=json.load(open('$INBOX_REGISTRY')); print(d.get('$project',''))" 2>/dev/null)
    if [[ -n "$path" && -d "$path" ]]; then echo "$path"; return; fi
  fi
  echo "ERROR: Cannot resolve project '$project'" >&2; return 1
}

# Load per-project scan config from .monitor-codebase.json
# Returns space-separated list of absolute scan paths (or project root if no config)
get_scan_dirs() {
  local project_path="$1"
  local config_file="$project_path/.monitor-codebase.json"
  if [[ -f "$config_file" ]]; then
    python3 -c "
import json, os
cfg = json.load(open('$config_file'))
root = '$project_path'
dirs = cfg.get('include_dirs', ['.'])
for d in dirs:
    full = os.path.join(root, d)
    if os.path.isdir(full):
        print(full)
" 2>/dev/null
  else
    echo "$project_path"
  fi
}

# Build find/grep exclude args from config
get_exclude_dirs() {
  local project_path="$1"
  local config_file="$project_path/.monitor-codebase.json"
  # NOTE: .venv* patterns are handled by find -name '.venv*' below, not just exact match
  local defaults=".venv venv node_modules __pycache__ .git dist build .eggs .mypy_cache .pytest_cache .uv .cache site-packages archive-v0 .tox .ruff_cache .venv-batch .venv_old .venv.bak"
  if [[ -f "$config_file" ]]; then
    local extra
    extra=$(python3 -c "
import json
cfg = json.load(open('$config_file'))
print(' '.join(cfg.get('exclude_dirs', [])))
" 2>/dev/null)
    echo "$defaults $extra"
  else
    echo "$defaults"
  fi
}

project_git_root() {
  local project_path="$1"
  git -C "$project_path" rev-parse --show-toplevel 2>/dev/null || return 1
}

commit_all_changes_if_needed() {
  local repo_root="$1"
  local commit_message="$2"

  if [[ -z "$repo_root" ]]; then
    return 1
  fi

  local status_output
  status_output=$(git -C "$repo_root" status --porcelain 2>/dev/null || true)
  if [[ -z "$status_output" ]]; then
    return 0
  fi

  git -C "$repo_root" add -A
  git -C "$repo_root" commit -m "$commit_message"
}

normalize_fix_plan_for_orchestrate() {
  local source_plan="$1"
  local output_plan="$2"
  local project_path="$3"
  local project_name="$4"

  (
    cd "$SKILLS_DIR/orchestrate"
    uv run python - "$source_plan" "$output_plan" "$project_path" "$project_name" <<'PY'
from pathlib import Path
import sys
import yaml

source_plan = Path(sys.argv[1])
output_plan = Path(sys.argv[2])
project_path = Path(sys.argv[3]).resolve()
project_name = sys.argv[4]

data = yaml.safe_load(source_plan.read_text()) or {}
tasks = data.get("tasks") or []

normalized = {
    "version": 1,
    "kind": "orchestrate-plan",
    "repo_root": str(project_path),
    "metadata": {
        "title": data.get("plan") or f"monitor-codebase-fix-{project_name}",
        "goal": data.get("description") or f"Apply skills-ci fixes for {project_name}",
        "source_yaml": str(source_plan.resolve()),
    },
    "execution": {
        "max_concurrency": 1,
    },
    "capability_overlap": [
        "skills-ci generates deterministic Tier 2 fixes and orchestrate executes them via code-runner.",
    ],
    "questions_blockers": [
        "None",
    ],
    "tasks": tasks,
    "lanes": [
        {"id": "default", "label": "Default"},
    ],
}

output_plan.write_text(yaml.safe_dump(normalized, sort_keys=False))
PY
  )
}

# Run find scoped to configured dirs with exclusions
scoped_find() {
  local project_path="$1"; shift
  local scan_dirs
  scan_dirs=$(get_scan_dirs "$project_path")
  local exclude_dirs
  exclude_dirs=$(get_exclude_dirs "$project_path")

  # Build -not -path exclusions
  local excludes=()
  for d in $exclude_dirs; do
    excludes+=(-not -path "*/$d/*")
  done

  for dir in $scan_dirs; do
    find "$dir" "${excludes[@]}" "$@" 2>/dev/null
  done
}

list_all_projects() {
  if [[ ! -f "$INBOX_REGISTRY" ]]; then echo "ERROR: No registry at $INBOX_REGISTRY" >&2; return 1; fi
  python3 "$SKILL_DIR/monitor_registry.py" list-enabled --registry "$INBOX_REGISTRY"
}

detect_best_practices() {
  # Detect which best-practices apply using scoped dirs (not compgen on full tree)
  local project_path="$1"
  local checks=()
  local scan_dirs
  scan_dirs=$(get_scan_dirs "$project_path")

  for dir in $scan_dirs; do
    if find "$dir" -name '*.py' -not -path '*/.venv/*' -not -path '*/node_modules/*' -print -quit 2>/dev/null | grep -q .; then
      checks+=("best-practices-python"); break
    fi
  done
  for dir in $scan_dirs; do
    if find "$dir" \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \) -not -path '*/node_modules/*' -print -quit 2>/dev/null | grep -q .; then
      checks+=("best-practices-react"); break
    fi
  done
  for dir in $scan_dirs; do
    if find "$dir" \( -name '*.rs' -o -name 'Cargo.toml' \) -not -path '*/target/*' -not -path '*/node_modules/*' -print -quit 2>/dev/null | grep -q .; then
      checks+=("best-practices-rust"); break
    fi
  done
  for dir in $scan_dirs; do
    if find "$dir" \( -path '*/prompts/*' -o -name '*prompt*.md' -o -name '*prompt*.txt' \) -not -path '*/node_modules/*' -print -quit 2>/dev/null | grep -q .; then
      checks+=("best-practices-prompt"); break
    fi
  done
  if [[ -d "$project_path/plasmoids" ]]; then checks+=("best-practices-kde"); fi
  for dir in $scan_dirs; do
    if find "$dir" -path '*/skills/*/SKILL.md' -print -quit 2>/dev/null | grep -q .; then
      checks+=("best-practices-skills"); break
    fi
  done
  if [[ -d "$project_path/streamdeck" ]]; then checks+=("best-practices-streamdeck"); fi
  printf '%s\n' "${checks[@]}"
}

run_best_practices_checks() {
  local project_path="$1" project_name="$2"
  local violations=()
  local bp_skills
  bp_skills=$(detect_best_practices "$project_path")

  while IFS= read -r bp; do
    [[ -z "$bp" ]] && continue
    case "$bp" in
      best-practices-skills)
        while IFS= read -r skill_md; do
          [[ -z "$skill_md" ]] && continue
          local skill_dir
          skill_dir=$(dirname "$skill_md")
          local sname
          sname=$(basename "$skill_dir")
          [[ ! -f "$skill_dir/run.sh" ]] && violations+=("{\"rule\":\"missing-run-sh\",\"skill\":\"$bp\",\"target\":\"$sname\"}")
          [[ ! -f "$skill_dir/sanity.sh" ]] && violations+=("{\"rule\":\"missing-sanity-sh\",\"skill\":\"$bp\",\"target\":\"$sname\"}")
        done < <(scoped_find "$project_path" -path '*/skills/*/SKILL.md' -type f)
        ;;
      best-practices-react)
        # Fast TypeScript/React best-practices scan on TS/JS source files
        while IFS= read -r source_file; do
          [[ -z "$source_file" ]] && continue
          local rel_path
          rel_path=$(python3 -c "import os; print(os.path.relpath('$source_file', '$project_path'))" 2>/dev/null)
          local line_count
          line_count=$(wc -l < "$source_file" 2>/dev/null || echo 0)

          # Large file check (>500 lines for TS/JS is a code smell)
          if [[ "$line_count" -gt 500 ]]; then
            violations+=("{\"rule\":\"typescript-large-file\",\"skill\":\"$bp\",\"target\":\"$rel_path\",\"detail\":\"${line_count} lines\"}")
          fi

          local content
          content=$(cat "$source_file" 2>/dev/null || true)

          case "$source_file" in
            *.tsx|*.jsx)
              # Missing data-testid on interactive elements (buttons, inputs, links)
              if echo "$content" | grep -qE '<(button|input|a |select|textarea)' && ! echo "$content" | grep -q 'data-testid'; then
                violations+=("{\"rule\":\"react-missing-testid\",\"skill\":\"$bp\",\"target\":\"$rel_path\"}")
              fi

              # Missing useRegisterAction for QuerySpec/voice control
              if echo "$content" | grep -qE '<(button|input|select)' && ! echo "$content" | grep -q 'useRegisterAction'; then
                violations+=("{\"rule\":\"react-missing-queryspec\",\"skill\":\"$bp\",\"target\":\"$rel_path\"}")
              fi

              # Missing aria-label on interactive elements
              if echo "$content" | grep -qE '<(button|img|svg|canvas)' && ! echo "$content" | grep -qE 'aria-label|aria-labelledby|role='; then
                violations+=("{\"rule\":\"react-missing-aria\",\"skill\":\"$bp\",\"target\":\"$rel_path\"}")
              fi

              # Hardcoded SVG dimensions (should use viewBox — best-practices-d3 rule)
              if echo "$content" | grep -qE '<svg.*width="[0-9]' && ! echo "$content" | grep -q 'viewBox'; then
                violations+=("{\"rule\":\"d3-hardcoded-svg\",\"skill\":\"best-practices-d3\",\"target\":\"$rel_path\"}")
              fi

              # Mouse events instead of pointer events
              if echo "$content" | grep -qE 'onMouse(Enter|Leave|Over|Out)'; then
                violations+=("{\"rule\":\"react-mouse-events\",\"skill\":\"$bp\",\"target\":\"$rel_path\"}")
              fi
              ;;
          esac

          # Barrel file imports (import from index — kills tree shaking)
          if echo "$content" | grep -qE "from ['\"]\.\.?/['\"]|from ['\"]\.\.?/index['\"]"; then
            violations+=("{\"rule\":\"react-barrel-import\",\"skill\":\"$bp\",\"target\":\"$rel_path\"}")
          fi

        done < <(scoped_find "$project_path" \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \) -type f)
        ;;
      best-practices-rust)
        # Fast Rust best-practices scan; quality_checks.py owns line-level routing.
        if [[ ! -f "$project_path/Cargo.toml" ]]; then
          violations+=("{\"rule\":\"rust-missing-cargo-manifest\",\"skill\":\"$bp\",\"target\":\"$project_name\"}")
        fi
        while IFS= read -r rust_file; do
          [[ -z "$rust_file" ]] && continue
          local rel_path
          rel_path=$(python3 -c "import os; print(os.path.relpath('$rust_file', '$project_path'))" 2>/dev/null)
          local line_count
          line_count=$(wc -l < "$rust_file" 2>/dev/null || echo 0)
          if [[ "$line_count" -gt 500 ]]; then
            violations+=("{\"rule\":\"rust-large-file\",\"skill\":\"$bp\",\"target\":\"$rel_path\",\"detail\":\"${line_count} lines\"}")
          fi
        done < <(scoped_find "$project_path" -name '*.rs' -type f)
        ;;
      best-practices-prompt)
        # Prompt-specific line-level findings and review-prompt routes are emitted by quality_checks.py.
        ;;
      best-practices-d3)
        # D3 checks via the skill's run.sh check command
        if [[ -x "$SKILLS_DIR/best-practices-d3/run.sh" ]]; then
          local d3_output
          d3_output=$("$SKILLS_DIR/best-practices-d3/run.sh" check "$project_path" 2>/dev/null || true)
          local d3_count
          d3_count=$(echo "$d3_output" | grep -c "potential violations" 2>/dev/null || echo 0)
          if [[ "$d3_count" -gt 0 ]]; then
            violations+=("{\"rule\":\"d3-violations\",\"skill\":\"best-practices-d3\",\"target\":\"$project_name\",\"detail\":\"$d3_count violations\"}")
          fi
        fi
        ;;
    esac
  done <<< "$bp_skills"

  if [[ ${#violations[@]} -eq 0 ]]; then
    echo "[]"
  else
    printf '[%s]' "$(IFS=,; echo "${violations[*]}")"
  fi
}

scan_project() {
  local project_name="$1" do_fix="${2:-false}"
  local project_path
  project_path=$(resolve_project_path "$project_name")
  local report_file="$ARTIFACTS_DIR/${project_name}_${TIMESTAMP}.json"
  local scan_start_time
  scan_start_time=$(date +%s)
  local scan_dirs
  scan_dirs=$(get_scan_dirs "$project_path")
  local python_file_count
  python_file_count=$(scoped_find "$project_path" -type f -name '*.py' | python3 -c "import sys; print(len({line.strip() for line in sys.stdin if line.strip()}))" 2>/dev/null || echo 0)

  # Per-step timeout budgets (seconds), based on measured p95 durations:
  #   project-state: 30s (LLM call)
  #   cleanup:       60s (file scan + LLM)
  #   quality_checks: 5s (AST, fast)
  #   security-scan: 180s (semgrep + gitleaks + pip-audit — slowest step)
  #   duplication:    5s (AST, fast)
  #   dep_graph:      5s (AST, fast)
  #   coverage:       5s (AST, fast)
  #   ingest-code:   60s (treesitter + embedding)
  #   skills-ci:    120s (full scan if skills dir exists)
  #   dogpile:       60s (web research)
  #   aggregate:      5s (JSON merge)
  #   trend:          5s (z-score + memory store)
  # Total per-project budget: ~545s (~9min). Round up to 600s.
  local PER_PROJECT_BUDGET=600
  local project_timeout
  project_timeout=$(get_project_timeout "$project_path")
  # Use the smaller of config timeout and measured budget
  if [[ "$project_timeout" -gt "$PER_PROJECT_BUDGET" ]]; then
    project_timeout="$PER_PROJECT_BUDGET"
  fi
  # Per-step: use measured budgets, not equal division
  STEP_TIMEOUT=180  # security-scan is the bottleneck; other steps use their own timeouts

  echo "=== Scanning: $project_name ($project_path) [budget: ${project_timeout}s, step_max: ${STEP_TIMEOUT}s] ==="

  # Step 1: project-state (focused on health, missing features, competitive landscape)
  echo "[1/10] Running project-state..."
  local ps_file="$ARTIFACTS_DIR/${project_name}_project_state.json"
  (cd "$project_path" && run_skill_timed project-state report --quick --json > "$ps_file" 2>/dev/null) || echo '{"error":"project-state timeout or failed"}' > "$ps_file"

  # Step 2: cleanup dry-run (dead files, stale docs, junk artifacts)
  echo "[2/10] Running cleanup --dry-run..."
  local cl_file="$ARTIFACTS_DIR/${project_name}_cleanup.json"
  (cd "$project_path" && run_skill_timed cleanup --dry-run > "$cl_file" 2>/dev/null) || echo '{"error":"cleanup timeout or failed"}' > "$cl_file"

  # Step 3: best-practices grep checks (fast, shell-based)
  echo "[3/10] Running best-practices grep checks..."
  local bp_violations
  bp_violations=$(run_best_practices_checks "$project_path" "$project_name")
  local bp_file="$ARTIFACTS_DIR/${project_name}_best_practices.json"
  printf '%s\n' "$bp_violations" > "$bp_file"

  # Step 4: quality checks (AST-based — inline prompts, regex classifiers,
  #   handwritten tests, mock-only tests, hardcoded paths, shell AQL, banned imports)
  echo "[4/10] Running quality checks (AST-based)..."
  local qc_file="$ARTIFACTS_DIR/${project_name}_quality_checks.json"
  local include_dir_args=""
  for d in $scan_dirs; do
    # Convert absolute scan dir to relative path from project root
    local rel_dir
    rel_dir=$(python3 -c "import os; print(os.path.relpath('$d', '$project_path'))" 2>/dev/null)
    if [[ -n "$include_dir_args" ]]; then
      include_dir_args="$include_dir_args,$rel_dir"
    else
      include_dir_args="$rel_dir"
    fi
  done
  python3 "$SKILL_DIR/quality_checks.py" "$project_path" --json > "$qc_file" 2>/dev/null || echo '{"error":"quality checks failed"}' > "$qc_file"

  # Step 4.5: security scan (SAST, vulnerable deps, secrets)
  echo "[4.5/10] Running security scan..."
  local sec_file="$ARTIFACTS_DIR/${project_name}_security.json"
  local sec_raw_file="$ARTIFACTS_DIR/${project_name}_security.raw"
  if (
    cd "$project_path" &&
    run_skill_timed security-scan --format json scan --path "$project_path" > "$sec_raw_file" 2>/dev/null &&
    write_json_object_from_output "$sec_raw_file" "$sec_file"
  ); then
    rm -f "$sec_raw_file"
  else
    echo '{"error":"security scan failed"}' > "$sec_file"
    rm -f "$sec_raw_file"
  fi

  # Step 4.6: duplication scan (only for non-trivial Python projects)
  echo "[4.6/10] Running duplication detection..."
  local dup_file="$ARTIFACTS_DIR/${project_name}_duplicates.json"
  if [[ "$python_file_count" -gt 10 ]]; then
    python3 "$SKILL_DIR/duplication_detector.py" $scan_dirs > "$dup_file" 2>/dev/null || echo '{"error":"duplication scan failed"}' > "$dup_file"
  else
    printf '{"skipped":"python file count <= 10","python_file_count":%s}\n' "$python_file_count" > "$dup_file"
  fi

  # Step 4.7: dependency graph analysis
  echo "[4.7/10] Running dependency graph analysis..."
  local dep_file="$ARTIFACTS_DIR/${project_name}_deps.json"
  python3 "$SKILL_DIR/dep_graph.py" $scan_dirs > "$dep_file" 2>/dev/null || echo '{"error":"dependency graph scan failed"}' > "$dep_file"

  # Step 4.8: test coverage analysis
  echo "[4.8/10] Running test coverage analysis..."
  local coverage_file="$ARTIFACTS_DIR/${project_name}_coverage.json"
  python3 "$SKILL_DIR/coverage_tracker.py" $scan_dirs > "$coverage_file" 2>/dev/null || echo '{"error":"coverage analysis failed"}' > "$coverage_file"

  # Step 5: auto-fix docstrings (only in --fix mode — scan is read-only)
  if [[ "$do_fix" == "true" ]]; then
    echo "[5/10] Auto-fixing missing docstrings..."
    for d in $scan_dirs; do
      python3 "$SKILL_DIR/autofix_docstrings.py" "$d" 2>&1 || true
    done
  else
    echo "[5/10] Docstring autofix skipped (scan mode is read-only, use --fix)"
  fi

  # Step 6: ingest-code rescan (scoped to configured dirs)
  echo "[6/10] Running ingest-code rescan..."
  local last_run_file="$ARTIFACTS_DIR/${project_name}_last_run"
  local since="7d"
  if [[ -f "$last_run_file" ]]; then
    since=$(cat "$last_run_file")
  fi
  local ingest_args=(rescan --since "$since" --treesitter --code-index --scope "monitor-$project_name")
  for d in $scan_dirs; do
    ingest_args+=(-c "$d")
  done
  local ingest_file="$ARTIFACTS_DIR/${project_name}_ingest_code.json"
  local ingest_raw_file="$ARTIFACTS_DIR/${project_name}_ingest_code.raw"
  if (run_skill_timed ingest-code "${ingest_args[@]}" > "$ingest_raw_file" 2>/dev/null) && write_json_object_from_output "$ingest_raw_file" "$ingest_file"; then
    rm -f "$ingest_raw_file"
  else
    echo '{"error":"ingest-code timeout or failed"}' > "$ingest_file"
    rm -f "$ingest_raw_file"
  fi
  date -u +%Y-%m-%dT%H:%M:%SZ > "$last_run_file"

  # Step 6.1: verify code-symbol Qdrant embedding coverage for expected script files
  echo "[6.1/10] Verifying code embedding coverage..."
  local embedding_file="$ARTIFACTS_DIR/${project_name}_embedding_coverage.json"
  python3 "$SKILL_DIR/embedding_coverage.py" "$project_path" \
    --project-name "$project_name" \
    --scope "monitor-$project_name" \
    --json > "$embedding_file" 2>/dev/null || echo '{"error":"embedding coverage audit failed"}' > "$embedding_file"

  # Step 7: skills-ci scan (if project has skills)
  echo "[7/10] Checking for skills-ci targets..."
  local sci_file="$ARTIFACTS_DIR/${project_name}_skills_ci.json"
  local skills_root=""
  for d in $scan_dirs; do
    if [[ -d "$d/skills" ]]; then skills_root="$d/skills"; break; fi
    if [[ -d "$d/.pi/skills" ]]; then skills_root="$d/.pi/skills"; break; fi
  done
  if [[ -n "$skills_root" ]]; then
    echo "  Running skills-ci on $skills_root..."
    (cd "$SKILLS_DIR/skills-ci" && timeout "$STEP_TIMEOUT" uv run python skills_ci.py --mode scan --root "$skills_root" --report-json "$sci_file" 2>/dev/null) || echo '{"error":"skills-ci timeout or failed"}' > "$sci_file"
  else
    echo '{"skipped":"no skills directory found"}' > "$sci_file"
  fi

  # Step 8: focused dogpile for improvement ideas (only if violations found)
  echo "[8/10] Researching improvements..."
  local dogpile_file="$ARTIFACTS_DIR/${project_name}_improvements.txt"
  local qc_total
  qc_total=$(python3 -c "import json; print(json.load(open('$qc_file')).get('total_violations',0))" 2>/dev/null || echo 0)
  local bp_count
  bp_count=$(python3 -c "import json; print(len(json.loads('$bp_violations')))" 2>/dev/null || echo 0)
  local circular_dep_count
  circular_dep_count=$(python3 -c "import json; print(len(json.load(open('$dep_file')).get('circular_deps', [])))" 2>/dev/null || echo 0)
  local embedding_issue_count
  embedding_issue_count=$(python3 -c "import json; d=json.load(open('$embedding_file')); print((d.get('missing_files_count', 0) or 0) + (d.get('unsynced_files_count', 0) or 0) if d.get('status') != 'pass' else 0)" 2>/dev/null || echo 0)
  local total_issues=$((qc_total + bp_count + circular_dep_count + embedding_issue_count))

  if [[ "$total_issues" -gt 5 ]]; then
    local top_rules
    top_rules=$(python3 -c "
import json
d = json.load(open('$qc_file'))
rules = d.get('by_rule', {})
top = sorted(rules.items(), key=lambda x: -x[1])[:3]
print(', '.join(f'{r}({c})' for r, c in top))
" 2>/dev/null || echo "various")
    local dogpile_query="fix common violations in Python project: $top_rules"
    if [[ "$circular_dep_count" -gt 0 ]]; then
      dogpile_query="$dogpile_query; circular dependencies found ($circular_dep_count cycles)"
    fi
    run_skill_timed dogpile search "$dogpile_query" --no-interactive > "$dogpile_file" 2>/dev/null || echo "dogpile timeout or unavailable" > "$dogpile_file"
  else
    echo "Low violation count ($total_issues) — skipping dogpile research" > "$dogpile_file"
  fi

  # Step 9: aggregate report
  echo "[9/10] Aggregating findings..."
  python3 "$SKILL_DIR/fallow_contract.py" aggregate \
    --project-name "$project_name" \
    --project-path "$project_path" \
    --timestamp "$TIMESTAMP" \
    --output "$report_file" \
    --project-state "$ps_file" \
    --cleanup "$cl_file" \
    --best-practices "$bp_file" \
    --quality-checks "$qc_file" \
    --security-scan "$sec_file" \
    --duplication-scan "$dup_file" \
    --dependency-graph "$dep_file" \
    --coverage-analysis "$coverage_file" \
    --ingest-code "$ingest_file" \
    --embedding-coverage "$embedding_file" \
    --skills-ci "$sci_file" \
    2>/dev/null || echo "{\"error\":\"report aggregation failed\",\"project\":\"$project_name\"}" > "$report_file"

  # Step 9.5: compare against previous report trend + anomaly detection
  echo "[9.5/10] Comparing trend with previous report..."
  local trend_delta="STABLE"
  local prev=""
  prev=$(ls -t "$ARTIFACTS_DIR"/${project_name}_2*.json 2>/dev/null | sed -n '2p' || true)

  local trend_json=""
  trend_json=$(python3 "$SKILL_DIR/trend_tracker.py" "$project_name" "$report_file" "$prev" 2>/dev/null) || true
  if [[ -n "$trend_json" ]]; then
    trend_delta=$(python3 -c "import json; print(json.loads('$trend_json').get('trend', 'STABLE'))" 2>/dev/null || echo "STABLE")
    # Inject anomalies and trend into the report JSON
    python3 -c "
import json, sys
trend = json.loads('$trend_json')
with open('$report_file') as f:
    report = json.load(f)
report['trend'] = trend.get('trend', 'STABLE')
report['anomalies'] = trend.get('anomalies', [])
if trend.get('anomalies'):
    warns = report.get('notifications', {}).get('discord_warnings', [])
    warns.append(f\"SPIKE: {len(trend['anomalies'])} anomalous categories detected\")
    report.setdefault('notifications', {})['discord_warnings'] = warns
with open('$report_file', 'w') as f:
    json.dump(report, f, indent=2)
" 2>/dev/null || true
  elif [[ -n "$prev" && -f "$prev" ]]; then
    # Fallback: simple delta if trend_tracker fails
    trend_delta=$(python3 -c "
import json
def lt(p):
    try:
        return int(json.load(open(p)).get('summary',{}).get('total_issues',0))
    except Exception:
        return 0
d=lt('$report_file')-lt('$prev')
print(f'REGRESSION (+{d})' if d>0 else f'IMPROVED ({d})' if d<0 else 'STABLE')
" 2>/dev/null || echo "STABLE")
  fi

  # Persist to memory
  local total_issues
  total_issues=$(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('total_issues',0))" 2>/dev/null || echo 0)
  local sast_findings
  sast_findings=$(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('sast_findings',0))" 2>/dev/null || echo 0)
  local vulnerable_deps
  vulnerable_deps=$(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('vulnerable_deps',0))" 2>/dev/null || echo 0)
  local secrets_found
  secrets_found=$(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('secrets_found',0))" 2>/dev/null || echo 0)
  local security_total
  security_total=$(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('total_security_findings',0))" 2>/dev/null || echo 0)
  local coverage_pct
  coverage_pct=$(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('coverage_pct',0.0))" 2>/dev/null || echo 0.0)
  local summary_text
 summary_text=$(python3 -c "
import json
r = json.load(open('$report_file'))
s = r.get('summary', {})
parts = []
if s.get('total_bp_violations'): parts.append(f\"{s['total_bp_violations']} best-practices\")
if s.get('total_quality_violations'): parts.append(f\"{s['total_quality_violations']} quality\")
if s.get('total_security_findings'): parts.append(f\"{s['total_security_findings']} security\")
if s.get('duplicate_functions'): parts.append(f\"{s['duplicate_functions']} duplicates\")
if s.get('circular_dependencies'): parts.append(f\"{s['circular_dependencies']} circular deps\")
parts.append(f\"coverage {s.get('coverage_pct', 0.0):.2f}%\")
parts.append(f\"embeddings {s.get('embedding_coverage_pct', 100.0):.2f}%\")
if s.get('embedding_coverage_issues'): parts.append(f\"{s['embedding_coverage_issues']} embedding coverage issues\")
if s.get('skills_ci_errors'): parts.append(f\"{s['skills_ci_errors']} skills-ci errors\")
print(', '.join(parts) if parts else 'clean')
" 2>/dev/null || echo "unknown")

  run_skill memory learn \
    -p "monitor-codebase scan of $project_name: $total_issues total issues ($summary_text, $trend_delta)" \
    -s "Report: $report_file. Quality checks: $qc_total. Best-practices: $bp_count. Security: SAST $sast_findings, deps $vulnerable_deps, secrets $secrets_found ($security_total total). Duplicates: $(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('duplicate_functions',0))" 2>/dev/null || echo 0). Circular deps: $(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('circular_dependencies',0))" 2>/dev/null || echo 0). Coverage: $coverage_pct%. Embedding coverage: $(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('embedding_coverage_pct',100.0))" 2>/dev/null || echo 100.0)%. Trend: $trend_delta." \
    --scope "monitor-codebase" 2>/dev/null || true

  echo "Report: $report_file ($total_issues issues: $summary_text, $trend_delta)"

  # Record execution duration to /memory for timeout estimation
  local scan_end_time
  scan_end_time=$(date +%s)
  local scan_duration=$((scan_end_time - scan_start_time))
  python3 "$SKILLS_DIR/common/estimate_timeout.py" record \
    --skill monitor-codebase \
    --duration "$scan_duration" \
    --units 1 \
    --outcome success \
    --trigger "${TRIGGER:-manual}" \
    --cmd "scan $project_name" \
    --composed project-state cleanup quality-checks security-scan ingest-code skills-ci dogpile \
    2>/dev/null || true

  # Step 10: Local fix execution via skills-ci → /orchestrate
  if [[ "$do_fix" == "true" && "$total_issues" -gt 0 ]]; then
    echo "[10/10] Running local fix pipeline via skills-ci → /orchestrate ($total_issues issues)..."
    local sci_violation_count
    sci_violation_count=$(python3 -c "import json; print(len(json.load(open('$sci_file')).get('violations', [])))" 2>/dev/null || echo 0)
    if [[ "$sci_violation_count" -eq 0 ]]; then
      echo "  No skills-ci violations available for fix-plan generation; skipping orchestrated fixes"
      return
    fi

    local repo_root=""
    repo_root=$(project_git_root "$project_path" 2>/dev/null || true)
    if [[ -n "$repo_root" ]]; then
      echo "  Creating safety commit in $repo_root..."
      commit_all_changes_if_needed \
        "$repo_root" \
        "monitor-codebase: safety snapshot before orchestrated fixes for $project_name ($TIMESTAMP)"
    else
      echo "  Skipping safety commit: $project_path is not a git repository"
    fi

    local raw_fix_plan="$ARTIFACTS_DIR/${project_name}_skills_ci_fix_plan_raw.yaml"
    local fix_plan="$ARTIFACTS_DIR/${project_name}_skills_ci_fix_plan.yaml"
    echo "  Generating fix plan from $sci_file..."
    (
      cd "$SKILLS_DIR/skills-ci"
      timeout "$STEP_TIMEOUT" uv run python generate_fix_plan.py \
        --report "$sci_file" \
        --output "$raw_fix_plan"
    )

    if [[ ! -s "$raw_fix_plan" ]]; then
      echo "  No fix plan generated; skipping orchestrated fixes"
      return
    fi

    normalize_fix_plan_for_orchestrate "$raw_fix_plan" "$fix_plan" "$project_path" "$project_name"

    local fix_task_count
    fix_task_count=$(rg -c '^[[:space:]]*- id:' "$fix_plan" 2>/dev/null || echo 0)
    if [[ "$fix_task_count" -eq 0 ]]; then
      echo "  Fix plan contains no executable tasks; skipping /orchestrate"
      return
    fi

    echo "  Executing $fix_task_count fix tasks via /orchestrate..."
    timeout "$project_timeout" "$SKILLS_DIR/orchestrate/run.sh" run "$fix_plan"

    if [[ -n "$repo_root" ]]; then
      echo "  Committing orchestrated fixes..."
      commit_all_changes_if_needed \
        "$repo_root" \
        "monitor-codebase: apply orchestrated fixes for $project_name ($TIMESTAMP)"
    fi
  fi
}

cmd_audit() {
  local base_ref=""
  local output_file=""
  local project_name=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --base) base_ref="$2"; shift 2 ;;
      --output) output_file="$2"; shift 2 ;;
      *) project_name="$1"; shift ;;
    esac
  done
  if [[ -z "$project_name" ]]; then
    echo "Usage: $0 audit <project> [--base REF] [--output path]" >&2
    return 1
  fi

  local project_path
  project_path=$(resolve_project_path "$project_name")
  local audit_prefix="$ARTIFACTS_DIR/${project_name}_audit_${TIMESTAMP}"
  local report_file="${output_file:-${audit_prefix}.json}"
  local changed_file="${audit_prefix}_changed_files.txt"
  local scan_dirs
  scan_dirs=$(get_scan_dirs "$project_path")
  local python_file_count
  python_file_count=$(scoped_find "$project_path" -type f -name '*.py' | python3 -c "import sys; print(len({line.strip() for line in sys.stdin if line.strip()}))" 2>/dev/null || echo 0)

  if [[ -n "$base_ref" ]]; then
    git -C "$project_path" diff --name-only "${base_ref}...HEAD" -- > "$changed_file" 2>/dev/null || \
      git -C "$project_path" diff --name-only "$base_ref" HEAD -- > "$changed_file" 2>/dev/null || \
      : > "$changed_file"
  else
    local bootstrap_file="$audit_prefix.bootstrap.json"
    python3 "$SKILL_DIR/fallow_contract.py" audit \
      --project-name "$project_name" \
      --project-path "$project_path" \
      --timestamp "$TIMESTAMP" \
      --output "$bootstrap_file" \
      >/dev/null 2>&1 || true
    base_ref=$(python3 - "$bootstrap_file" <<'PY'
import json
import sys
from pathlib import Path

try:
    print(json.loads(Path(sys.argv[1]).read_text()).get("base_ref", ""))
except Exception:
    print("")
PY
)
    python3 - "$bootstrap_file" "$changed_file" <<'PY'
import json
import sys
from pathlib import Path

bootstrap = Path(sys.argv[1])
out = Path(sys.argv[2])
try:
    data = json.loads(bootstrap.read_text())
    out.write_text("\n".join(data.get("changed_files", [])) + "\n")
except Exception:
    out.write_text("")
PY
    rm -f "$bootstrap_file"
  fi

  echo "=== Auditing: $project_name ($project_path) ==="
  echo "Changed files: $(python3 -c "from pathlib import Path; print(len([l for l in Path('$changed_file').read_text().splitlines() if l.strip()]))" 2>/dev/null || echo 0)"

  local bp_violations
  bp_violations=$(run_best_practices_checks "$project_path" "$project_name")
  local bp_file="${audit_prefix}_best_practices.json"
  printf '%s\n' "$bp_violations" > "$bp_file"

  local qc_file="${audit_prefix}_quality_checks.json"
  python3 "$SKILL_DIR/quality_checks.py" "$project_path" --json > "$qc_file" 2>/dev/null || echo '{"error":"quality checks failed"}' > "$qc_file"

  local dup_file="${audit_prefix}_duplicates.json"
  if [[ "$python_file_count" -gt 10 ]]; then
    python3 "$SKILL_DIR/duplication_detector.py" $scan_dirs > "$dup_file" 2>/dev/null || echo '{"error":"duplication scan failed"}' > "$dup_file"
  else
    printf '{"skipped":"python file count <= 10","python_file_count":%s}\n' "$python_file_count" > "$dup_file"
  fi

  local dep_file="${audit_prefix}_deps.json"
  python3 "$SKILL_DIR/dep_graph.py" $scan_dirs > "$dep_file" 2>/dev/null || echo '{"error":"dependency graph scan failed"}' > "$dep_file"

  local coverage_file="${audit_prefix}_coverage.json"
  python3 "$SKILL_DIR/coverage_tracker.py" $scan_dirs > "$coverage_file" 2>/dev/null || echo '{"error":"coverage analysis failed"}' > "$coverage_file"

  local embedding_file="${audit_prefix}_embedding_coverage.json"
  python3 "$SKILL_DIR/embedding_coverage.py" "$project_path" \
    --project-name "$project_name" \
    --scope "monitor-$project_name" \
    --json > "$embedding_file" 2>/dev/null || echo '{"error":"embedding coverage audit failed"}' > "$embedding_file"

  local aggregate_status=0
  python3 "$SKILL_DIR/fallow_contract.py" audit \
    --project-name "$project_name" \
    --project-path "$project_path" \
    --timestamp "$TIMESTAMP" \
    --output "$report_file" \
    --base-ref "$base_ref" \
    --changed-files-file "$changed_file" \
    --best-practices "$bp_file" \
    --quality-checks "$qc_file" \
    --duplication-scan "$dup_file" \
    --dependency-graph "$dep_file" \
    --coverage-analysis "$coverage_file" \
    --embedding-coverage "$embedding_file" || aggregate_status=$?

  local verdict
  verdict=$(python3 -c "import json; print(json.load(open('$report_file')).get('verdict','warn'))" 2>/dev/null || echo "warn")
  local finding_count
  finding_count=$(python3 -c "import json; print(json.load(open('$report_file')).get('summary',{}).get('total_findings',0))" 2>/dev/null || echo 0)
  echo "Audit report: $report_file ($finding_count findings, verdict=$verdict)"
  return "$aggregate_status"
}

light_scan_project() {
  # For unchanged projects: refresh project-state only. No violations scan,
  # no dogpile (too expensive for continuous background scans), no code modification.
  local project_name="$1"
  local project_path
  project_path=$(resolve_project_path "$project_name")

  echo "=== Light scan (unchanged): $project_name ==="

  echo "[1/1] Running project-state..."
  local ps_file="$ARTIFACTS_DIR/${project_name}_project_state.json"
  (cd "$project_path" && run_skill project-state report --quick --json > "$ps_file" 2>/dev/null) || echo '{"error":"project-state failed"}' > "$ps_file"

  echo "Light scan complete: $project_name (project-state refreshed)"
}

has_project_changed() {
  # Check if project has new commits or tracked worktree changes since last full scan
  local project_name="$1"
  local project_path
  project_path=$(resolve_project_path "$project_name") || return 0  # scan if can't resolve
  local hash_file="$ARTIFACTS_DIR/${project_name}_last_hash"

  if [[ ! -d "$project_path/.git" ]]; then return 0; fi  # always scan non-git

  local current_hash worktree_state current_signature
  current_hash=$(git -C "$project_path" rev-parse HEAD 2>/dev/null)
  if [[ -z "$current_hash" ]]; then return 0; fi
  worktree_state=$(git -C "$project_path" status --porcelain --untracked-files=no 2>/dev/null || true)
  current_signature=$(printf '%s\n%s\n' "$current_hash" "$worktree_state" | sha256sum | awk '{print $1}')

  if [[ -f "$hash_file" ]]; then
    local stored_hash
    stored_hash=$(cat "$hash_file")
    if [[ "$current_signature" == "$stored_hash" ]]; then
      return 1  # unchanged
    fi
  fi

  echo "$current_signature" > "$hash_file"
  return 0  # changed
}

cmd_scan() {
  local do_fix=false
  local force_all=false
  local targets=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --all) targets=($(list_all_projects)); shift ;;
      --fix) do_fix=true; shift ;;
      --force) force_all=true; shift ;;
      *)     targets+=("$1"); shift ;;
    esac
  done
  if [[ ${#targets[@]} -eq 0 ]]; then echo "Usage: $0 scan <project|--all> [--fix] [--force]"; exit 1; fi

  local changed=0 unchanged=0 skipped=0 total=${#targets[@]}
  for proj in "${targets[@]}"; do
    # Skip projects that can't be resolved (moved/deleted)
    if ! resolve_project_path "$proj" > /dev/null 2>&1; then
      echo "=== Skipping $proj (cannot resolve path) ==="
      skipped=$((skipped + 1))
      continue
    fi
    if [[ "$force_all" == "true" ]] || has_project_changed "$proj"; then
      scan_project "$proj" "$do_fix"
      changed=$((changed + 1))
    else
      light_scan_project "$proj"
      unchanged=$((unchanged + 1))
    fi
  done

  echo ""
  echo "=== Scan complete: $changed full, $unchanged light, $skipped skipped (of $total projects) ==="
}

cmd_report() {
  local project="${1:-}"
  if [[ -z "$project" ]]; then
    echo "Latest scan reports:"
    ls -lt "$ARTIFACTS_DIR"/*_2*.json 2>/dev/null | head -20
    return
  fi
  local latest
  latest=$(ls -t "$ARTIFACTS_DIR"/${project}_2*.json 2>/dev/null | head -1)
  if [[ -z "$latest" ]]; then echo "No reports found for $project"; return 1; fi
  echo "=== Latest report: $project ==="
  python3 -c "import json; d=json.load(open('$latest')); print(json.dumps(d, indent=2))"
}

cmd_schedule() {
  local COMMON="$SKILLS_DIR/common"

  local projects
  projects=($(list_all_projects))
  local total=${#projects[@]}
  # Worst case: all projects changed → all full scans
  local timeout
  timeout=$(python3 "$COMMON/estimate_timeout.py" --full "$total" --light 0)

  run_skill scheduler register \
    --name "monitor-codebase" \
    --cron "*/30 * * * *" \
    --command "$SKILL_DIR/run.sh scan --all" \
    --workdir "$PI_MONO" \
    --timeout "$timeout" \
    --description "Continuous codebase health scan every 30 minutes for all registered projects"
  echo "Registered continuous scan every 30 minutes (timeout: ${timeout}s for $total projects)"
}

cmd_estimate() {
  # Estimate total runtime using shared estimate_timeout.py (single source of truth
  # for all per-step budgets measured from p95 benchmarks).
  local COMMON="$SKILLS_DIR/common"

  local projects
  projects=($(list_all_projects))
  local total=${#projects[@]}
  local full=0 light=0 skip=0

  for proj in "${projects[@]}"; do
    if ! resolve_project_path "$proj" > /dev/null 2>&1; then
      skip=$((skip + 1))
      continue
    fi
    if has_project_changed "$proj"; then
      full=$((full + 1))
    else
      light=$((light + 1))
    fi
  done

  local result
  result=$(python3 "$COMMON/estimate_timeout.py" --full "$full" --light "$light" --json)
  local timeout
  timeout=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin)['timeout_seconds'])")
  local human
  human=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin)['timeout_human'])")

  echo "=== Runtime Estimate for scan --all ==="
  echo "Projects: $total total ($full changed → full scan, $light unchanged → light scan, $skip missing → skip)"
  echo "Estimated timeout: ${timeout}s ($human)"
  echo ""
  echo "Recommended scheduler timeout: ${timeout}"
}

cmd_cache_state() {
  python3 "$SKILL_DIR/cache_state.py" "$@"
}

cmd_create_pr() {
  # Create a PR with a violation summary from the latest nightly fix run.
  # Usage: run.sh create-pr [--base main] [--title "..."]
  local base_branch="main"
  local title=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --base) base_branch="$2"; shift 2 ;;
      --title) title="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  local current_branch
  current_branch=$(git -C "$PI_MONO" branch --show-current)
  if [[ "$current_branch" == "$base_branch" ]]; then
    echo "ERROR: Already on $base_branch — nightly fixes should be on a separate branch" >&2
    return 1
  fi

  # Gather latest reports for PR body
  local report_files
  report_files=$(ls -t "$ARTIFACTS_DIR"/*_2*.json 2>/dev/null | head -10)
  local pr_body
  pr_body=$(python3 -c "
import json, sys
from pathlib import Path

files = '''$report_files'''.strip().split('\n')
sections = []
total_issues = 0
total_fixed = 0

for f in files:
    f = f.strip()
    if not f:
        continue
    try:
        data = json.load(open(f))
    except Exception:
        continue
    project = data.get('project', Path(f).stem.split('_')[0])
    summary = data.get('summary', {})
    issues = summary.get('total_issues', 0)
    trend = data.get('trend', 'UNKNOWN')
    anomalies = data.get('anomalies', [])
    total_issues += issues

    line = f'| {project} | {issues} | {trend} |'
    if anomalies:
        line += ' \u26a0\ufe0f SPIKE'
    sections.append(line)

print('## Nightly Codebase Health Report')
print()
print('| Project | Issues | Trend |')
print('|---------|--------|-------|')
for s in sections:
    print(s)
print()
print(f'**Total issues across all projects: {total_issues}**')
print()

# Per-category breakdown from first report
if files:
    try:
        first = json.load(open(files[0].strip()))
        s = first.get('summary', {})
        print('### Breakdown (latest project)')
        print(f'- Best-practices: {s.get(\"total_bp_violations\", 0)}')
        print(f'- Quality: {s.get(\"total_quality_violations\", 0)}')
        print(f'- Security: {s.get(\"total_security_findings\", 0)}')
        print(f'- Duplicates: {s.get(\"duplicate_functions\", 0)}')
        print(f'- Circular deps: {s.get(\"circular_dependencies\", 0)}')
        print(f'- Coverage: {s.get(\"coverage_pct\", 0.0):.1f}%')
        print(f'- Skills CI errors: {s.get(\"skills_ci_errors\", 0)}')
    except Exception:
        pass
print()
print('---')
print('Generated by \`/monitor-codebase\` nightly pipeline')
" 2>/dev/null)

  if [[ -z "$title" ]]; then
    title="nightly: monitor-codebase health fixes ($(date +%Y-%m-%d))"
  fi

  # Push and create PR
  git -C "$PI_MONO" push -u origin "$current_branch" 2>/dev/null || true

  gh pr create \
    --repo "$(git -C "$PI_MONO" remote get-url origin | sed 's/.*github.com[:/]\(.*\)\.git/\1/')" \
    --base "$base_branch" \
    --title "$title" \
    --body "$pr_body"
}

cmd_pr_comment() {
  # Add a violation summary comment to an existing PR.
  # Usage: run.sh pr-comment <pr_number> [project]
  local pr_number="${1:?PR number required}"
  local project="${2:-}"

  local report_file=""
  if [[ -n "$project" ]]; then
    report_file=$(ls -t "$ARTIFACTS_DIR"/${project}_2*.json 2>/dev/null | head -1)
  else
    report_file=$(ls -t "$ARTIFACTS_DIR"/*_2*.json 2>/dev/null | head -1)
  fi

  if [[ -z "$report_file" || ! -f "$report_file" ]]; then
    echo "ERROR: No report found" >&2
    return 1
  fi

  local comment_body
  comment_body=$(python3 -c "
import json
data = json.load(open('$report_file'))
project = data.get('project', 'unknown')
s = data.get('summary', {})
trend = data.get('trend', 'UNKNOWN')
anomalies = data.get('anomalies', [])

print(f'## Monitor-Codebase: {project}')
print(f'**Trend: {trend}**')
print()
print(f'| Metric | Count |')
print(f'|--------|-------|')
print(f'| Total issues | {s.get(\"total_issues\", 0)} |')
print(f'| Best-practices | {s.get(\"total_bp_violations\", 0)} |')
print(f'| Quality | {s.get(\"total_quality_violations\", 0)} |')
print(f'| Security | {s.get(\"total_security_findings\", 0)} |')
print(f'| Duplicates | {s.get(\"duplicate_functions\", 0)} |')
print(f'| Circular deps | {s.get(\"circular_dependencies\", 0)} |')
print(f'| Coverage | {s.get(\"coverage_pct\", 0.0):.1f}% |')
print(f'| Skills CI errors | {s.get(\"skills_ci_errors\", 0)} |')

if anomalies:
    print()
    print('### Anomalies Detected')
    for a in anomalies:
        print(f'- **{a[\"category\"]}**: current={a[\"current\"]}, mean={a[\"mean\"]}, z={a[\"z_score\"]} ({a[\"severity\"]})')
" 2>/dev/null)

  gh pr comment "$pr_number" --body "$comment_body"
  echo "Comment added to PR #$pr_number"
}

cmd_visualize() {
  # Generate dependency graph and health visualizations for a project.
  # Usage: run.sh visualize <project> [--format png|svg|pdf] [--output dir]
  local project="${1:?Project name required}"; shift
  local format="svg"
  local output_dir="$ARTIFACTS_DIR"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --format) format="$2"; shift 2 ;;
      --output) output_dir="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  local project_path
  project_path=$(resolve_project_path "$project")
  mkdir -p "$output_dir"

  # 1. Dependency graph via /create-figure
  echo "=== Generating dependency graph for $project ==="
  local dep_output="$output_dir/${project}_deps.${format}"
  if [[ -x "$SKILLS_DIR/create-figure/run.sh" ]]; then
    run_skill create-figure deps \
      --project "$project_path" \
      --output "$dep_output" \
      --format "$format" \
      --backend graphviz 2>/dev/null || echo "[WARN] create-figure deps failed"
    if [[ -f "$dep_output" ]]; then
      echo "Dependency graph: $dep_output"
    fi
  else
    echo "[SKIP] create-figure skill not found"
  fi

  # 2. Violation heatmap from latest scan report
  local latest_report
  latest_report=$(ls -t "$ARTIFACTS_DIR"/${project}_2*.json 2>/dev/null | head -1)
  if [[ -n "$latest_report" && -x "$SKILLS_DIR/create-figure/run.sh" ]]; then
    echo "=== Generating health heatmap ==="
    local heatmap_output="$output_dir/${project}_health.${format}"
    run_skill create-figure metrics \
      --input "$latest_report" \
      --output "$heatmap_output" \
      --type bar \
      --title "$project: Violation Breakdown" \
      --format "$format" 2>/dev/null || echo "[WARN] create-figure metrics failed"
    if [[ -f "$heatmap_output" ]]; then
      echo "Health chart: $heatmap_output"
    fi
  fi

  # 3. Trend chart from history
  local trend_history="$ARTIFACTS_DIR/trend_history_${project}.json"
  if [[ -f "$trend_history" && -x "$SKILLS_DIR/create-figure/run.sh" ]]; then
    echo "=== Generating trend chart ==="
    local trend_output="$output_dir/${project}_trend.${format}"
    run_skill create-figure metrics \
      --input "$trend_history" \
      --output "$trend_output" \
      --type line \
      --title "$project: Issue Trend" \
      --format "$format" 2>/dev/null || echo "[WARN] create-figure trend failed"
    if [[ -f "$trend_output" ]]; then
      echo "Trend chart: $trend_output"
    fi
  fi
}

case "${1:-help}" in
  scan)        shift; cmd_scan "$@" ;;
  audit)       shift; cmd_audit "$@" ;;
  report)      shift; cmd_report "$@" ;;
  estimate)    cmd_estimate ;;
  cache-state) shift; cmd_cache_state "$@" ;;
  create-pr)   shift; cmd_create_pr "$@" ;;
  pr-comment)  shift; cmd_pr_comment "$@" ;;
  visualize)   shift; cmd_visualize "$@" ;;
  schedule)    cmd_schedule ;;
  help|*)
    echo "monitor-codebase — Continuous codebase health monitoring"
    echo ""
    echo "Commands:"
    echo "  scan <project|--all> [--fix] [--force]  Scan project(s) for violations"
    echo "  audit <project> [--base REF] [--output path]  Changed-file audit with verdict"
    echo "  report [project]              Show latest findings"
    echo "  estimate                      Estimate runtime for scan --all"
    echo "  cache-state [project...] [--force]  Refresh project-state for changed projects"
    echo "  create-pr [--base main] [--title ...]  Create PR with violation summary"
    echo "  pr-comment <pr_number> [project]  Add violation comment to a PR"
    echo "  visualize <project> [--format svg|png|pdf]  Generate dep graph + health charts"
    echo "  schedule                      Register continuous 30-minute scan with calculated timeout"
    ;;
esac
