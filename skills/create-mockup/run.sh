#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV 2>/dev/null || true

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$(cd "$SKILL_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
/create-mockup — canonical design front door

Usage:
  ./run.sh new [html] <mockup-lab args...>
  ./run.sh bakeoff <brief/context args...>
  ./run.sh new assets <create-image args...>
  ./run.sh improve review <review-design args...>
  ./run.sh improve iterate <mockup-lab iterate args...>
  ./run.sh ship ux <ux-lab args...>
  ./run.sh ship review <review-design args...>
  ./run.sh ship test <test-interactions args...>
  ./run.sh route
  ./run.sh help

Examples:
  ./run.sh new --brief "PromptFoo-style eval dashboard" --screenshots ref.png --output out/
  ./run.sh new html --spec spec.md
  ./run.sh bakeoff --brief SPARTA_CHAT_BRIEF.md --models claude,openai,gemini,opencode-kimi --baseline-url http://127.0.0.1:4319/ --persona brandon-bailey --constraints cots,nvis,embry-style,not-dashboard --output ./design-bakeoff/sparta-chat
  ./run.sh new assets generate "abstract nebula background" --output nebula.png
  ./run.sh improve review review --persona nico-bailon --input screenshot.png
  ./run.sh improve iterate --project 123 --screen abc --feedback "Reduce chrome"
  ./run.sh ship ux start
  ./run.sh ship test full --url "http://localhost:3000" --persona margaret-chen --manifest manifest.json
EOF
}

route() {
  cat <<'EOF'
Canonical flow:
  new      -> mockup-lab (+ create-image for assets, review-design for critique)
  bakeoff  -> ask concurrent model fanout (+ scillm batch/SSE progress where available), render candidates, then review-design
  improve  -> review-design, then mockup-lab iterate, then review-design again
  ship     -> ux-lab, best-practices-react, test-interactions, final review-design

Use HTML/CSS for UI mockups.
Use create-image only for supporting assets or visual references.
Use bakeoff when the user wants N independent model-created interface candidates.
Reject another legacy clunky chat-dashboard hybrid when the brief says "not a dashboard".
EOF
}

bakeoff_guide() {
  cat <<'EOF'
Bakeoff flow:
  1. Capture/import the baseline design and write baseline/failure-analysis.md
  2. Capture/import reference screenshots and write references/takeaways.md
  3. Write one shared brief with product context, constraints, anti-goals, and scoring rubric
  4. Use /ask for concurrent model fanout; /ask should use bounded /scillm batch/as_completed or SSE streaming where available
  5. Generate one static HTML/CSS candidate per model with rationale
  6. Render candidates and capture screenshots
  7. Run /review-design with the same persona/rubric across all candidates
  8. Publish an HTML comparison board with tabs, score matrix, and winner or hybrid plan

Required anti-goal:
  Do not create another legacy clunky chat-dashboard hybrid when the user asked for a chat-first interface.

Reference handling:
  Use screenshots to extract qualities such as calm density, spacing, typography, and input affordances.
  Do not clone Gemini, Claude, ChatGPT, Raycast, Linear, or other product chrome unless explicitly requested.

Recommended lanes:
  claude        visual hierarchy and compliance-audit tone
  openai        implementation-realistic product UI
  gemini        alternate visual direction
  opencode-kimi information architecture and state mechanics

Run this command with --brief and --output to execute the shared bakeoff runner.
Candidate generation is concurrent and writes per-lane status artifacts.
EOF
}

cmd_bakeoff() {
  local has_brief=0
  local has_output=0
  for arg in "$@"; do
    case "$arg" in
      --brief)
        has_brief=1
        ;;
      --output)
        has_output=1
        ;;
    esac
  done

  if [[ $# -eq 0 || $has_brief -eq 0 || $has_output -eq 0 ]]; then
    bakeoff_guide
    if [[ $# -ne 0 ]]; then
      echo >&2
      echo "bakeoff requires --brief <file> and --output <dir>." >&2
      exit 2
    fi
    return 0
  fi

  exec python3 "$SKILL_DIR/scripts/bakeoff.py" "$@"
}

cmd_new() {
  local mode="${1:-}"
  if [[ "$mode" == "assets" ]]; then
    shift
    exec "$SKILLS_DIR/create-image/run.sh" "$@"
  fi

  if [[ "$mode" == "html" ]]; then
    shift
  fi

  local has_spec=0
  local has_visual_ref=0
  for arg in "$@"; do
    case "$arg" in
      --spec)
        has_spec=1
        ;;
      --image|--images|--screenshot|--screenshots|--reference|--references)
        has_visual_ref=1
        ;;
    esac
  done

  if [[ $has_spec -eq 1 && $has_visual_ref -eq 0 ]]; then
    exec "$SKILLS_DIR/mockup-lab/run.sh" generate "$@"
  fi

  exec "$SKILLS_DIR/mockup-lab/run.sh" mockup "$@"
}

improve_guide() {
  cat <<'EOF'
Improve flow:
  1. Run `./run.sh improve review ...` to critique the current UI
  2. Run `./run.sh improve iterate ...` to apply redesign feedback in mockup-lab
  3. Re-run review-design before moving to ship
EOF
}

cmd_improve() {
  local action="${1:-guide}"
  case "$action" in
    review)
      shift
      exec "$SKILLS_DIR/review-design/run.sh" "$@"
      ;;
    iterate)
      shift
      exec "$SKILLS_DIR/mockup-lab/run.sh" iterate "$@"
      ;;
    guide|help|"")
      improve_guide
      ;;
    *)
      echo "Unknown improve action: $action" >&2
      improve_guide >&2
      exit 1
      ;;
  esac
}

ship_guide() {
  cat <<'EOF'
Ship flow:
  1. Use `./run.sh ship ux ...` for implementation work in ux-lab
  2. Apply best-practices-react during implementation
  3. Use `./run.sh ship test ...` for live-DOM verification
  4. Use `./run.sh ship review ...` for final visual drift review
EOF
}

cmd_ship() {
  local action="${1:-guide}"
  case "$action" in
    ux)
      shift
      exec "$SKILLS_DIR/ux-lab/run.sh" "$@"
      ;;
    review)
      shift
      exec "$SKILLS_DIR/review-design/run.sh" "$@"
      ;;
    test)
      shift
      exec "$SKILLS_DIR/test-interactions/run.sh" "$@"
      ;;
    guide|help|"")
      ship_guide
      ;;
    *)
      echo "Unknown ship action: $action" >&2
      ship_guide >&2
      exit 1
      ;;
  esac
}

main() {
  local cmd="${1:-help}"
  shift || true

  case "$cmd" in
    new)
      cmd_new "$@"
      ;;
    bakeoff)
      cmd_bakeoff "$@"
      ;;
    improve)
      cmd_improve "$@"
      ;;
    ship)
      cmd_ship "$@"
      ;;
    route)
      route
      ;;
    help|--help|-h|"")
      usage
      ;;
    *)
      echo "Unknown command: $cmd" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
