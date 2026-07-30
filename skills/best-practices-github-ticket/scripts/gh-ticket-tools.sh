#!/usr/bin/env bash
set -euo pipefail

export GH_PROMPT_DISABLED="${GH_PROMPT_DISABLED:-1}"
export GH_PAGER="${GH_PAGER:-cat}"
export NO_COLOR="${NO_COLOR:-1}"
export GH_NO_UPDATE_NOTIFIER="${GH_NO_UPDATE_NOTIFIER:-1}"
export GH_NO_EXTENSION_UPDATE_NOTIFIER="${GH_NO_EXTENSION_UPDATE_NOTIFIER:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/templates"

repo_args=()
DRY_RUN=0
PARSED=0

usage() {
    cat <<'EOF'
Usage:
  gh-ticket-tools.sh doctor [--repo owner/name]
  gh-ticket-tools.sh ensure-labels [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh search [--repo owner/name] [--label label] [--search query] [--limit N] [--dry-run]
  gh-ticket-tools.sh next [--repo owner/name] [--label label] [--limit N] [--dry-run]
  gh-ticket-tools.sh show ISSUE [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh lease ISSUE --agent AGENT [--assign-me] [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh comment ISSUE --body FILE [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh block ISSUE --reason FILE [--release] [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh unblock ISSUE --reason FILE [--agent AGENT] [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh release ISSUE --agent AGENT --reason FILE [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh close ISSUE --proof FILE [--review FILE] [--reason completed|not-planned] [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh close-duplicate ISSUE --duplicate-of ISSUE --proof FILE [--review FILE] [--repo owner/name] [--dry-run]
  gh-ticket-tools.sh proof-template [proof|blocker|progress|review]

Agent workflow:
  0. Run doctor before mutation.
  1. Run ensure-labels once per repo, preferably dry-run first.
  2. Search or next for one open ticket that is not active, blocked, or external-owned.
  3. Show the ticket and read body/comments before acting.
  4. Lease exactly one ticket before work.
  5. Comment progress, blockers, review, or proof from files.
  6. Close only with a non-empty proof file, after `lease --agent` set maintainer-active. --reason is completed|not-planned.
  7. If blocked, `block` adds maintainer-blocked + needs-human (keep or --release the lease).
  8. When the blocker clears, `unblock ISSUE --reason FILE [--agent NAME]` removes both labels (and re-leases with --agent) so you can close. block --release does NOT clear the labels.

Rules:
  - Never close without a proof file.
  - Never work two leased tickets at once.
  - Live release/close paths audit registered worktrees before removing a lease.
  - Never lease or close tickets labeled needs-human or external-owner. To close a resolved-but-blocked ticket, `unblock` it first (do not raw `gh issue edit`).
  - Use --dry-run before first mutation in a new repo.
  - Common flags --repo/-R and --dry-run are valid anywhere after the command.
  - The last output line for successful mutations is machine-readable JSON.
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 2
}

need_gh() {
    command -v gh >/dev/null 2>&1 || die "gh CLI not found"
}

quote_cmd() {
    printf '%q ' "$@"
    printf '\n'
}

json_ok() {
    local action="$1"
    shift
    printf '{"ok":true,"action":"%s"' "$action"
    while [[ $# -gt 0 ]]; do
        printf ',"%s":"%s"' "$1" "$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g')"
        shift 2
    done
    printf '}\n'
}

run_gh() {
    if [[ "$DRY_RUN" == "1" ]]; then
        quote_cmd "$@"
    else
        need_gh
        "$@"
    fi
}

parse_common_flag() {
    PARSED=0
    case "${1:-}" in
        --repo|-R)
            [[ $# -ge 2 ]] || die "$1 requires owner/name"
            repo_args=(--repo "$2")
            PARSED=2
            ;;
        --dry-run)
            DRY_RUN=1
            PARSED=1
            ;;
    esac
}

require_file() {
    local label="$1"
    local file="$2"
    [[ -f "$file" ]] || die "$label file not found: $file"
    [[ -s "$file" ]] || die "$label file is empty: $file"
}

audit_worktrees_for_retention() {
    [[ "$DRY_RUN" == "1" ]] && return 0
    if [[ "${GH_TICKET_SKIP_WORKTREE_AUDIT:-}" == "1" ]]; then
        echo "WARN skipping worktree retention audit because GH_TICKET_SKIP_WORKTREE_AUDIT=1" >&2
        return 0
    fi
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "WARN not inside a git worktree; worktree retention audit skipped" >&2
        return 0
    fi
    local repo_root
    repo_root="$(git rev-parse --show-toplevel)"
    "$SCRIPT_DIR/audit-worktrees.sh" --repo "$repo_root" --json >&2 || die \
        "worktree retention audit failed; commit, remove, or explicitly retain flagged secondary worktrees before releasing/closing the ticket"
}

issue_label_names() {
    local issue="$1"
    need_gh
    gh issue view "$issue" "${repo_args[@]}" --json labels --jq '.labels[].name'
}

issue_has_label() {
    local issue="$1"
    local label="$2"
    issue_label_names "$issue" | grep -Fxq "$label"
}

assert_ticket_mutable() {
    local issue="$1"
    [[ "$DRY_RUN" == "1" ]] && return 0
    if issue_has_label "$issue" "maintainer-active"; then
        die "issue $issue already has maintainer-active"
    fi
    if issue_has_label "$issue" "needs-human"; then
        die "issue $issue has needs-human"
    fi
    if issue_has_label "$issue" "external-owner"; then
        die "issue $issue has external-owner"
    fi
}

assert_ticket_closable() {
    local issue="$1"
    [[ "$DRY_RUN" == "1" ]] && return 0
    if ! issue_has_label "$issue" "maintainer-active"; then
        die "issue $issue is not leased with maintainer-active"
    fi
    if issue_has_label "$issue" "needs-human"; then
        die "issue $issue has needs-human"
    fi
    if issue_has_label "$issue" "external-owner"; then
        die "issue $issue has external-owner"
    fi
}

cmd_doctor() {
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        die "unknown doctor arg: $1"
    done
    need_gh
    gh auth status >/dev/null
    gh issue list "${repo_args[@]}" --limit 1 >/dev/null
    local missing=()
    local label
    for label in skill-bug skill-maintenance skill-optimization agent-bug agent-maintenance agent-optimization skills-ci monitor-skill-health type:bug type:feature type:optimization type:maintenance type:question needs-triage maintainer-active maintainer-blocked needs-human external-owner route:backend_python_or_skill_runtime agent:agent-skill-maintainer; do
        if ! gh label list "${repo_args[@]}" --search "$label" --json name --jq '.[].name' | grep -Fxq "$label"; then
            missing+=("$label")
        fi
    done
    if [[ "${#missing[@]}" -gt 0 ]]; then
        printf 'WARN missing_labels=%s\n' "$(IFS=,; echo "${missing[*]}")"
        printf 'NEXT gh-ticket-tools.sh ensure-labels'
        [[ "${#repo_args[@]}" -gt 0 ]] && printf ' --repo %s' "${repo_args[1]}"
        printf ' --dry-run\n'
    fi
    json_ok doctor status ok missing_label_count "${#missing[@]}"
}

cmd_search() {
    local label=""
    local search=""
    local limit="100"
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --label)
                [[ $# -ge 2 ]] || die "--label requires a value"
                label="$2"; shift 2 ;;
            --search)
                [[ $# -ge 2 ]] || die "--search requires a query"
                search="$2"; shift 2 ;;
            --limit)
                [[ $# -ge 2 ]] || die "--limit requires a value"
                limit="$2"; shift 2 ;;
            *) die "unknown search arg: $1" ;;
        esac
    done
    local cmd=(gh issue list "${repo_args[@]}" --state open --json number,title,labels,url,assignees,author,state,stateReason,createdAt,updatedAt --limit "$limit")
    [[ -n "$label" ]] && cmd+=(--label "$label")
    [[ -n "$search" ]] && cmd+=(--search "$search")
    run_gh "${cmd[@]}"
}

cmd_next() {
    local label=""
    local limit="20"
    local search="-label:maintainer-active -label:maintainer-blocked -label:needs-human -label:external-owner sort:updated-asc"
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --label)
                [[ $# -ge 2 ]] || die "--label requires a value"
                label="$2"; shift 2 ;;
            --limit)
                [[ $# -ge 2 ]] || die "--limit requires a value"
                limit="$2"; shift 2 ;;
            *) die "unknown next arg: $1" ;;
        esac
    done
    local cmd=(gh issue list "${repo_args[@]}" --state open --json number,title,labels,url,assignees,author,state,stateReason,createdAt,updatedAt --limit "$limit" --search "$search")
    [[ -n "$label" ]] && cmd+=(--label "$label")
    run_gh "${cmd[@]}"
}

cmd_show() {
    [[ $# -ge 1 ]] || die "show requires ISSUE"
    local issue="$1"; shift
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        die "unknown show arg: $1"
    done
    run_gh gh issue view "$issue" "${repo_args[@]}" --json number,title,body,labels,comments,url,assignees,author,state,stateReason,createdAt,updatedAt,closedAt
}

cmd_lease() {
    [[ $# -ge 1 ]] || die "lease requires ISSUE"
    local issue="$1"; shift
    local agent=""
    local assign_me=0
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --agent)
                [[ $# -ge 2 ]] || die "--agent requires a value"
                agent="$2"; shift 2 ;;
            --assign-me)
                assign_me=1; shift ;;
            *) die "unknown lease arg: $1" ;;
        esac
    done
    [[ -n "$agent" ]] || die "lease requires --agent"
    assert_ticket_mutable "$issue"
    local lease_id
    lease_id="$(date -u +%Y%m%dT%H%M%SZ)-${agent}-${issue}"
    run_gh gh issue edit "$issue" "${repo_args[@]}" --add-label maintainer-active
    if [[ "$assign_me" == "1" ]]; then
        run_gh gh issue edit "$issue" "${repo_args[@]}" --add-assignee @me
    fi
    run_gh gh issue comment "$issue" "${repo_args[@]}" --body "<!-- agent-lease
agent: ${agent}
lease_id: ${lease_id}
issue: ${issue}
-->

Lease: maintainer-active by ${agent}.
Scope: one ticket.
Closure requirement: deterministic proof comment before close."
    if [[ "$DRY_RUN" != "1" ]] && ! issue_has_label "$issue" "maintainer-active"; then
        die "lease verification failed: maintainer-active missing"
    fi
    json_ok lease issue "$issue" agent "$agent" lease_id "$lease_id"
}

cmd_comment() {
    [[ $# -ge 1 ]] || die "comment requires ISSUE"
    local issue="$1"; shift
    local body=""
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --body)
                [[ $# -ge 2 ]] || die "--body requires a file"
                body="$2"; shift 2 ;;
            *) die "unknown comment arg: $1" ;;
        esac
    done
    [[ -n "$body" ]] || die "comment requires --body FILE"
    require_file "body" "$body"
    run_gh gh issue comment "$issue" "${repo_args[@]}" --body-file "$body"
    json_ok comment issue "$issue" body "$body"
}

cmd_block() {
    [[ $# -ge 1 ]] || die "block requires ISSUE"
    local issue="$1"; shift
    local reason=""
    local release=0
    local -a blocked_by=()
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --reason)
                [[ $# -ge 2 ]] || die "--reason requires a file"
                reason="$2"; shift 2 ;;
            --release)
                release=1; shift ;;
            --blocked-by)
                [[ $# -ge 2 ]] || die "--blocked-by requires owner/repo#N"
                blocked_by+=("$2"); shift 2 ;;
            *) die "unknown block arg: $1" ;;
        esac
    done
    [[ -n "$reason" ]] || die "block requires --reason FILE"
    require_file "reason" "$reason"
    # Validate every upstream reference BEFORE mutating the downstream issue.
    # project-watchdog clears blocked:upstream by polling these; a reference it
    # cannot read would stall the downstream ticket forever rather than erroring,
    # so this fails closed instead.
    for ref in ${blocked_by[@]+"${blocked_by[@]}"}; do
        [[ -n "$ref" ]] || continue
        [[ "$ref" =~ ^[^/]+/[^#]+#[0-9]+$ ]] || die "malformed --blocked-by reference: $ref (want owner/repo#N)"
        local up_repo="${ref%%#*}"
        local up_num="${ref##*#}"
        gh issue view "$up_num" --repo "$up_repo" --json number >/dev/null 2>&1 \
            || die "--blocked-by reference is not readable: $ref"
    done
    if [[ "${#blocked_by[@]}" -gt 0 ]]; then
        run_gh gh issue edit "$issue" "${repo_args[@]}" --add-label blocked:upstream
    fi
    if [[ "$release" == "1" ]]; then
        audit_worktrees_for_retention
    fi
    run_gh gh issue edit "$issue" "${repo_args[@]}" --add-label maintainer-blocked --add-label needs-human
    if [[ "$release" == "1" ]]; then
        run_gh gh issue edit "$issue" "${repo_args[@]}" --remove-label maintainer-active
    fi
    run_gh gh issue comment "$issue" "${repo_args[@]}" --body-file "$reason"
    for ref in ${blocked_by[@]+"${blocked_by[@]}"}; do
        [[ -n "$ref" ]] || continue
        run_gh gh issue comment "$issue" "${repo_args[@]}" --body "blocked-by: $ref"
        local up_repo="${ref%%#*}"
        local up_num="${ref##*#}"
        run_gh gh issue edit "$up_num" --repo "$up_repo" --add-label blocks-downstream
        run_gh gh issue comment "$up_num" --repo "$up_repo" --body "blocks-downstream: this issue blocks ${ref%%#*}#${issue}"
    done
    json_ok block issue "$issue" reason "$reason" released "$release"
}

cmd_unblock() {
    # Inverse of block: clears maintainer-blocked + needs-human so a resolved
    # ticket can be closed via the tool. Pass --agent to re-lease (adds
    # maintainer-active) so the caller can close in one step. Without this a
    # blocked ticket cannot be closed except by a raw `gh issue edit`.
    [[ $# -ge 1 ]] || die "unblock requires ISSUE"
    local issue="$1"; shift
    local reason=""
    local agent=""
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --reason)
                [[ $# -ge 2 ]] || die "--reason requires a file"
                reason="$2"; shift 2 ;;
            --agent)
                [[ $# -ge 2 ]] || die "--agent requires a value"
                agent="$2"; shift 2 ;;
            *) die "unknown unblock arg: $1" ;;
        esac
    done
    [[ -n "$reason" ]] || die "unblock requires --reason FILE"
    require_file "reason" "$reason"
    run_gh gh issue edit "$issue" "${repo_args[@]}" --remove-label maintainer-blocked --remove-label needs-human
    if [[ -n "$agent" ]]; then
        run_gh gh issue edit "$issue" "${repo_args[@]}" --add-label maintainer-active
    fi
    run_gh gh issue comment "$issue" "${repo_args[@]}" --body-file "$reason"
    json_ok unblock issue "$issue" agent "$agent" reason "$reason"
}

cmd_release() {
    [[ $# -ge 1 ]] || die "release requires ISSUE"
    local issue="$1"; shift
    local agent=""
    local reason=""
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --agent)
                [[ $# -ge 2 ]] || die "--agent requires a value"
                agent="$2"; shift 2 ;;
            --reason)
                [[ $# -ge 2 ]] || die "--reason requires a file"
                reason="$2"; shift 2 ;;
            *) die "unknown release arg: $1" ;;
        esac
    done
    [[ -n "$agent" ]] || die "release requires --agent"
    [[ -n "$reason" ]] || die "release requires --reason FILE"
    require_file "reason" "$reason"
    audit_worktrees_for_retention
    run_gh gh issue comment "$issue" "${repo_args[@]}" --body-file "$reason"
    run_gh gh issue edit "$issue" "${repo_args[@]}" --remove-label maintainer-active
    json_ok release issue "$issue" agent "$agent" reason "$reason"
}

normalize_close_reason() {
    case "$1" in
        completed) printf 'completed' ;;
        not-planned|not_planned|"not planned") printf 'not planned' ;;
        *) die "unknown close reason: $1" ;;
    esac
}

gh_supports_duplicate_of() {
    [[ "$DRY_RUN" == "1" ]] && return 1
    need_gh
    gh issue close --help 2>/dev/null | grep -q -- '--duplicate-of'
}

cmd_close() {
    [[ $# -ge 1 ]] || die "close requires ISSUE"
    local issue="$1"; shift
    local proof=""
    local review=""
    local reason="completed"
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --proof)
                [[ $# -ge 2 ]] || die "--proof requires a file"
                proof="$2"; shift 2 ;;
            --review)
                [[ $# -ge 2 ]] || die "--review requires a file"
                review="$2"; shift 2 ;;
            --reason)
                [[ $# -ge 2 ]] || die "--reason requires a value"
                reason="$(normalize_close_reason "$2")"; shift 2 ;;
            *) die "unknown close arg: $1" ;;
        esac
    done
    [[ -n "$proof" ]] || die "close requires --proof FILE"
    require_file "proof" "$proof"
    [[ -z "$review" ]] || require_file "review" "$review"
    assert_ticket_closable "$issue"
    audit_worktrees_for_retention
    run_gh gh issue comment "$issue" "${repo_args[@]}" --body-file "$proof"
    if [[ -n "$review" ]]; then
        run_gh gh issue comment "$issue" "${repo_args[@]}" --body-file "$review"
    fi
    run_gh gh issue edit "$issue" "${repo_args[@]}" --remove-label maintainer-active
    run_gh gh issue close "$issue" "${repo_args[@]}" --reason "$reason"
    json_ok close issue "$issue" reason "$reason" proof "$proof"
}

cmd_close_duplicate() {
    [[ $# -ge 1 ]] || die "close-duplicate requires ISSUE"
    local issue="$1"; shift
    local duplicate_of=""
    local proof=""
    local review=""
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        case "$1" in
            --duplicate-of)
                [[ $# -ge 2 ]] || die "--duplicate-of requires ISSUE"
                duplicate_of="$2"; shift 2 ;;
            --proof)
                [[ $# -ge 2 ]] || die "--proof requires a file"
                proof="$2"; shift 2 ;;
            --review)
                [[ $# -ge 2 ]] || die "--review requires a file"
                review="$2"; shift 2 ;;
            *) die "unknown close-duplicate arg: $1" ;;
        esac
    done
    [[ -n "$duplicate_of" ]] || die "close-duplicate requires --duplicate-of ISSUE"
    [[ -n "$proof" ]] || die "close-duplicate requires --proof FILE"
    require_file "proof" "$proof"
    [[ -z "$review" ]] || require_file "review" "$review"
    assert_ticket_closable "$issue"
    audit_worktrees_for_retention
    run_gh gh issue comment "$issue" "${repo_args[@]}" --body-file "$proof"
    if [[ -n "$review" ]]; then
        run_gh gh issue comment "$issue" "${repo_args[@]}" --body-file "$review"
    fi
    run_gh gh issue edit "$issue" "${repo_args[@]}" --remove-label maintainer-active
    if gh_supports_duplicate_of; then
        run_gh gh issue close "$issue" "${repo_args[@]}" --duplicate-of "$duplicate_of"
    else
        run_gh gh issue close "$issue" "${repo_args[@]}" --reason "not planned"
    fi
    json_ok close-duplicate issue "$issue" duplicate_of "$duplicate_of" proof "$proof"
}

cmd_ensure_labels() {
    while [[ $# -gt 0 ]]; do
        parse_common_flag "$@"
        if [[ "$PARSED" -gt 0 ]]; then shift "$PARSED"; continue; fi
        die "unknown ensure-labels arg: $1"
    done
    local labels=(
        "skill-bug|0e8a16|Skill behavior or validation failure"
        "skill-maintenance|5319e7|General skill cleanup or optimization"
        "skill-optimization|fbca04|Measurable skill improvement"
        "agent-bug|0e8a16|Agent behavior or validation failure"
        "agent-maintenance|5319e7|General agent cleanup or optimization"
        "agent-optimization|fbca04|Measurable agent improvement"
        "skills-ci|1d76db|Issue came from skills-ci or sanity output"
        "monitor-skill-health|1d76db|Issue came from monitor-skill-health output"
        "type:bug|d73a4a|Defect or regression"
        "type:feature|0e8a16|New capability or changed behavior request"
        "type:optimization|fbca04|Measurable improvement request"
        "type:maintenance|cfd3d7|Cleanup or invariant-preserving work"
        "type:question|d4c5f9|Source-backed answer or decision requested"
        "needs-triage|ededed|Type route target or proof is unclear"
        "maintainer-active|0052cc|Agent has leased this ticket"
        "maintainer-blocked|b60205|Progress is blocked"
        "needs-human|d93f0b|Human input or authority required"
        "external-owner|6f42c1|Owner is outside this repository"
        "agent-work|0052cc|Ticket is routable to a cron-dispatched repair agent"
        # project-watchdog's own routing vocabulary. Without these, `gh issue
        # edit --add-label` fails and the lease silently does not happen, so the
        # in-flight guard sees nothing and the watchdog works ahead.
        "agent-active|0052cc|A repair agent holds this ticket"
        "agent-blocked|b60205|A repair attempt failed; needs a decision before retry"
        "agent-done|0e8a16|A repair agent finished this ticket"
        # Without this the closure audit's PASS silently fails to mark the
        # ticket and the same closure is re-audited forever.
        "closure-verified|0e8a16|Closure was reviewed by the audit panel and upheld"
        "route:backend_python_or_skill_runtime|1d76db|Maintainer route: backend Python or skill runtime"
        "route:design_or_ux|1d76db|Maintainer route: design or UX"
        "route:frontend_code|1d76db|Maintainer route: frontend code"
        "route:rust_or_binary|1d76db|Maintainer route: Rust or binary"
        "route:ops_or_scheduler|1d76db|Maintainer route: ops or scheduler"
        "route:documentation_or_report|1d76db|Maintainer route: documentation or report"
        "route:security_or_compliance|1d76db|Maintainer route: security or compliance"
        # Concurrency lanes. These are scheduling facts, not documentation:
        # project-watchdog will not dispatch two tickets in the same lane at
        # once, and treats a ticket with no lane as unschedulable while any
        # other ticket is in flight.
        "lane:fe|c2e0c6|Concurrency lane: frontend"
        "lane:be|c2e0c6|Concurrency lane: backend"
        "lane:data|c2e0c6|Concurrency lane: data"
        "lane:docs|c2e0c6|Concurrency lane: docs"
        "lane:ops|c2e0c6|Concurrency lane: ops"
        "lane:sec|c2e0c6|Concurrency lane: security"
        "agent:agent-skill-maintainer|5319e7|Requested repair agent: agent-skill-maintainer"
    )
    local item name color description
    for item in "${labels[@]}"; do
        IFS='|' read -r name color description <<<"$item"
        run_gh gh label create "$name" "${repo_args[@]}" --color "$color" --description "$description" --force
    done
    json_ok ensure-labels label_count "${#labels[@]}"
}

cmd_proof_template() {
    local kind="${1:-proof}"
    [[ $# -le 1 ]] || die "proof-template accepts at most one template name"
    case "$kind" in
        proof|blocker|progress|review)
            cat "$TEMPLATE_DIR/${kind}.md" ;;
        *) die "unknown template: $kind" ;;
    esac
}

[[ $# -gt 0 ]] || { usage; exit 2; }
cmd="$1"
shift

case "$cmd" in
    doctor) cmd_doctor "$@" ;;
    ensure-labels) cmd_ensure_labels "$@" ;;
    search) cmd_search "$@" ;;
    next) cmd_next "$@" ;;
    show) cmd_show "$@" ;;
    lease) cmd_lease "$@" ;;
    comment) cmd_comment "$@" ;;
    block) cmd_block "$@" ;;
    unblock) cmd_unblock "$@" ;;
    release) cmd_release "$@" ;;
    close) cmd_close "$@" ;;
    close-duplicate) cmd_close_duplicate "$@" ;;
    proof-template) cmd_proof_template "$@" ;;
    -h|--help|help) usage ;;
    *) die "unknown command: $cmd" ;;
esac
