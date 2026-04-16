#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

SCRIPTS="$SCRIPT_DIR/scripts"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"

# Parse --model flag from any position
MODEL_OVERRIDE=""
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--model" ]]; then
        MODEL_OVERRIDE="__NEXT__"
    elif [[ "$MODEL_OVERRIDE" == "__NEXT__" ]]; then
        MODEL_OVERRIDE="$arg"
        export CHUTES_TEXT_MODEL="$MODEL_OVERRIDE"
        export CHUTES_MODEL_ID="$MODEL_OVERRIDE"
    else
        ARGS+=("$arg")
    fi
done
set -- "${ARGS[@]}"

case "${1:-help}" in
    scan)
        shift
        python3 "$SCRIPTS/scan_soup.py" --skills-root "$SKILLS_DIR" "$@"
        ;;

    compose)
        shift
        TASK=""
        NAME=""
        EXTRA_ARGS=()
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --task) TASK="$2"; shift 2 ;;
                --name) NAME="$2"; shift 2 ;;
                *) EXTRA_ARGS+=("$1"); shift ;;
            esac
        done
        if [[ -z "$TASK" ]]; then
            echo "Usage: $0 compose --task 'description' [--name skill-name]"
            exit 1
        fi
        NAME_ARG=""
        [[ -n "$NAME" ]] && NAME_ARG="--name $NAME"
        python3 "$SCRIPTS/gap_detector.py" --task "$TASK" --skills-root "$SKILLS_DIR" \
            --manifest $NAME_ARG "${EXTRA_ARGS[@]}"
        ;;

    craft)
        shift
        MANIFEST="$1"
        if [[ -z "$MANIFEST" || ! -f "$MANIFEST" ]]; then
            echo "Usage: $0 craft <manifest.yml>"
            exit 1
        fi
        echo "=== [skill-lab] Crafting from manifest ==="
        # Phase 3: Route to lab skills for each CREATE capability
        python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPTS')
try:
    import yaml
    manifest = yaml.safe_load(open('$MANIFEST'))
except ImportError:
    manifest = json.loads(open('$MANIFEST').read())

creates = manifest.get('composition', {}).get('create', [])
if not creates:
    print('No capabilities to create - all requirements met!')
    sys.exit(0)

for item in creates:
    cap = item.get('capability', 'unknown')
    lab = item.get('lab')
    if lab:
        print(f'  CREATE: {cap} → craft via /{lab}')
        print(f'    Run: $SKILLS_DIR/{lab}/run.sh ...')
    else:
        print(f'  CREATE: {cap} → direct implementation')
"
        ;;

    scaffold)
        shift
        MANIFEST="$1"
        OUTPUT="${2:-}"
        if [[ -z "$MANIFEST" || ! -f "$MANIFEST" ]]; then
            echo "Usage: $0 scaffold <manifest.yml> [output-dir]"
            exit 1
        fi
        OUT_ARGS=""
        [[ -n "$OUTPUT" ]] && OUT_ARGS="--output $OUTPUT"
        python3 "$SCRIPTS/scaffolder.py" --manifest "$MANIFEST" $OUT_ARGS
        ;;

    validate)
        shift
        SKILL_DIR="${1:-.}"
        echo "=== [skill-lab] Validation Cascade ==="

        # T0: /skills-ci
        echo "T0: Running /skills-ci validation..."
        VALIDATOR="$SKILLS_DIR/best-practices-skills/scripts/validate_skill.py"
        if [[ -f "$VALIDATOR" ]]; then
            python3 "$VALIDATOR" "$SKILL_DIR" --skills-root "$SKILLS_DIR" || {
                echo "T0 FAILED - skill does not pass best-practices"
                exit 1
            }
        else
            echo "T0 SKIP - validator not found"
        fi

        # T1: Security scan
        echo "T1: Running security scan..."
        if [[ -x "$SKILLS_DIR/hack/run.sh" ]]; then
            "$SKILLS_DIR/hack/run.sh" audit "$SKILL_DIR" --tool semgrep 2>/dev/null || {
                echo "T1 WARN - security findings detected"
            }
        else
            echo "T1 SKIP - /hack not available"
        fi

        # Sanity check
        echo "Sanity: Running skill sanity..."
        if [[ -x "$SKILL_DIR/sanity.sh" ]]; then
            bash "$SKILL_DIR/sanity.sh" || {
                echo "Sanity FAILED"
                exit 1
            }
        else
            echo "Sanity SKIP - no sanity.sh"
        fi

        echo "=== Validation PASSED ==="
        ;;

    create)
        shift
        TASK=""
        NAME=""
        DOCKER=false
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --task) TASK="$2"; shift 2 ;;
                --name) NAME="$2"; shift 2 ;;
                --docker) DOCKER=true; shift ;;
                *) shift ;;
            esac
        done
        if [[ -z "$TASK" ]]; then
            echo "Usage: $0 create --task 'description' [--name skill-name] [--docker]"
            exit 1
        fi

        echo "=== [skill-lab] Full Lifecycle ==="
        echo "Task: $TASK"
        echo ""

        # Phase 1: Scan soup
        echo "Phase 1: Scanning skill soup..."
        python3 "$SCRIPTS/scan_soup.py" --skills-root "$SKILLS_DIR" 2>/dev/null

        # Phase 2: Detect gaps and generate manifest
        echo ""
        echo "Phase 2: Detecting capability gaps..."
        MANIFEST_FILE=$(mktemp /tmp/skill_lab_manifest_XXXX.yml)
        NAME_ARG=""
        [[ -n "$NAME" ]] && NAME_ARG="--name $NAME"
        python3 "$SCRIPTS/gap_detector.py" --task "$TASK" --skills-root "$SKILLS_DIR" \
            --manifest $NAME_ARG > "$MANIFEST_FILE"

        echo "  Manifest: $MANIFEST_FILE"
        echo ""

        # Phase 3: Craft (show what needs to be done)
        echo "Phase 3: Capabilities to craft..."
        "$0" craft "$MANIFEST_FILE"
        echo ""

        # Phase 4: Scaffold
        echo "Phase 4: Scaffolding skill..."
        "$0" scaffold "$MANIFEST_FILE"
        echo ""

        # Phase 5: Validate
        SKILL_NAME=$(python3 -c "
import sys, json
try:
    import yaml
    m = yaml.safe_load(open('$MANIFEST_FILE'))
except ImportError:
    m = json.loads(open('$MANIFEST_FILE').read())
print(m.get('name', 'new-skill'))
")
        echo "Phase 5: Validating $SKILL_NAME..."
        "$0" validate "$SKILLS_DIR/$SKILL_NAME"
        echo ""

        echo "Phase 6: Promotion"
        echo "  Skill installed at: $SKILLS_DIR/$SKILL_NAME"
        echo "  To broadcast: $SKILLS_DIR/skills-broadcast/run.sh sync"

        # Post-hook: register new skill in /memory
        if command -v memory-agent &>/dev/null; then
            echo "  Registering $SKILL_NAME in /memory..."
            memory-agent ingest-skills "$SKILLS_DIR" --skill "$SKILL_NAME" 2>/dev/null || true
        fi

        echo ""
        echo "=== [skill-lab] Complete ==="

        rm -f "$MANIFEST_FILE"
        ;;

    run)
        shift
        python3 "$SCRIPTS/composer.py" --skills-root "$SKILLS_DIR" "$@"
        ;;

    predict)
        shift
        python3 "$SCRIPTS/bond_predictor.py" --skills-root "$SKILLS_DIR" predict "$@"
        ;;

    chain)
        shift
        python3 "$SCRIPTS/bond_predictor.py" --skills-root "$SKILLS_DIR" chain "$@"
        ;;

    train)
        shift
        python3 "$SCRIPTS/bond_teacher.py" "$@"
        ;;

    warm-pond)
        shift
        python3 "$SCRIPTS/warm_pond.py" run --skills-root "$SKILLS_DIR" "$@"
        ;;

    bootstrap-pond)
        shift
        python3 "$SCRIPTS/warm_pond.py" bootstrap --skills-root "$SKILLS_DIR" "$@"
        ;;

    harvest)
        shift
        python3 "$SCRIPTS/bond_harvest.py" nightly --skills-root "$SKILLS_DIR" "$@"
        ;;

    bond-stats)
        python3 "$SCRIPTS/bond_harvest.py" stats
        ;;

    attractors)
        shift
        python3 "$SCRIPTS/bond_harvest.py" attractors "$@"
        ;;

    evolve)
        shift
        python3 "$SCRIPTS/bond_harvest.py" evolve --skills-root "$SKILLS_DIR" "$@"
        ;;

    chain-mine)
        shift
        python3 "$SCRIPTS/chain_miner.py" extract --skills-root "$SKILLS_DIR" "$@"
        ;;

    chain-stats)
        shift
        python3 "$SCRIPTS/chain_miner.py" stats "$@"
        ;;

    chain-export)
        shift
        python3 "$SCRIPTS/chain_miner.py" export "$@"
        ;;

    chain-prepare)
        shift
        python3 "$SCRIPTS/chain_miner.py" prepare "$@"
        ;;

    distill)
        shift
        python3 "$SCRIPTS/trajectory_distiller.py" distill "$@"
        ;;

    affinities)
        shift
        python3 "$SCRIPTS/trajectory_distiller.py" affinities "$@"
        ;;

    granularity)
        shift
        python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPTS')
from scan_soup import scan_soup
from pathlib import Path

graph = scan_soup(Path('$SKILLS_DIR'))
skills = graph.get('skills', {})

# Sort by composability score
ranked = sorted(skills.items(), key=lambda x: x[1].get('composability_score', 0))

json_mode = '--json' in sys.argv
if json_mode:
    print(json.dumps({
        'skills': {k: {
            'composability_score': v.get('composability_score', 0),
            'provides_count': v.get('provides_count', 0),
            'script_count': v.get('script_count', 0),
            'lines_of_code': v.get('lines_of_code', 0),
        } for k, v in ranked},
        'warnings': graph.get('granularity_warnings', []),
    }, indent=2))
else:
    print('=== Skill Granularity (SUBLEQ Lesson) ===')
    print()
    print(f'  {\"Skill\":<30} {\"Score\":>6} {\"Provides\":>8} {\"Scripts\":>8} {\"LOC\":>6}')
    print(f'  {\"-\"*30} {\"-\"*6} {\"-\"*8} {\"-\"*8} {\"-\"*6}')
    for name, info in ranked:
        score = info.get('composability_score', 0)
        flag = ' ⚠' if score < 0.3 and info.get('lines_of_code', 0) > 100 else ''
        print(f'  {name:<30} {score:>6.3f} {info.get(\"provides_count\", 0):>8} {info.get(\"script_count\", 0):>8} {info.get(\"lines_of_code\", 0):>6}{flag}')
    warnings = graph.get('granularity_warnings', [])
    if warnings:
        print(f'\n  ⚠ {len(warnings)} skills below composability threshold (0.3)')
        print(f'  These are too coarse-grained for effective warm pond composition.')
" "$@"
        ;;

    graph)
        shift
        python3 "$SCRIPTS/scan_soup.py" --skills-root "$SKILLS_DIR" --json "$@"
        ;;

    help|*)
        echo "skill-lab: Symbiogenic skill creation engine"
        echo ""
        echo "Commands:"
        echo "  scan                     Scan skill soup and build capability graph"
        echo "  scan --task '...'        Show which skills match a task"
        echo "  compose --task '...'     Generate composition manifest"
        echo "  craft <manifest.yml>     Craft missing capabilities"
        echo "  scaffold <manifest.yml>  Generate skill directory from manifest"
        echo "  validate <skill-dir>     Run validation cascade"
        echo "  create --task '...'      Full lifecycle (scan→compose→craft→validate→promote)"
        echo "  run --task '...'         Compose and run a skill pipeline for a task"
        echo "  run --task '...' --execute  Actually execute the pipeline"
        echo "  run --task '...' --dry-run  Preview execution without running"
        echo ""
        echo "Chain Mining (Transcript → Training Data):"
        echo "  chain-mine                       Extract skill chains from transcripts"
        echo "  chain-mine --min-skills 3        Chains with 3+ skills"
        echo "  chain-mine --max-sessions 500    Limit sessions processed"
        echo "  chain-stats                      Show stats from extracted chains"
        echo "  chain-export --output FILE --fmt jsonl  Export for /create-classifier"
        echo "  chain-export --with-rationale    Include rationale prompts for /create-gpt"
        echo "  chain-prepare                    Format data for /create-classifier + /create-gpt"
        echo ""
        echo "Bond Prediction (3-Tier Cascade):"
        echo "  predict --skill-a X --skill-b Y  Predict bond between two skills"
        echo "  chain --skills 'a,b,c'           Predict chain success probability"
        echo "  train bootstrap                  Bootstrap labels from /scillm teacher"
        echo "  train loop                       Full training loop (bootstrap→train→gate)"
        echo "  warm-pond --iterations 500       Run Docker-isolated simulations"
        echo "  warm-pond --task-type extraction  Task-informed sampling"
        echo "  bootstrap-pond --target-labels 100 Bootstrap labels via warm pond"
        echo "  harvest                          Nightly harvest (traces+battle+pond)"
        echo "  distill [--top-k N] [--dry-run]  Distill traces into patterns/lessons"
        echo "  affinities [--json]              Show learned vs static affinities"
        echo "  bond-stats                       Show training data statistics"
        echo ""
        echo "Other:"
        echo "  graph [--json]           Visualize/export capability graph"
        echo ""
        echo "Options:"
        echo "  --name NAME              Name for the new skill"
        echo "  --docker                 Docker-isolated creation"
        ;;
esac
