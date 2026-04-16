"""
Markdown renderer for create-context.

Takes a populated ContextData instance and produces the full CONTEXT.md
markdown output string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context import ContextData


def generate_markdown(data: ContextData, include_git: bool = True) -> str:
    """Generate CONTEXT.md content from collected data."""
    lines = []

    # Header
    lines.append(f"# CONTEXT.md - {data.title}")
    lines.append("")
    lines.append(f"**Last Updated**: {data.date}")
    lines.append(f"**Session Focus**: {data.focus}")
    if data.git_branch:
        lines.append(f"**Git Branch**: {data.git_branch}")
    if data.project_purpose:
        lines.append(f"**Purpose**: {data.project_purpose}")
    if data.project_type:
        lines.append(f"**Type**: {data.project_type}")
    if data.project_status:
        lines.append(f"**Status**: {data.project_status}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Companion Repos
    if data.companion_repos:
        lines.append("## Related Repositories")
        lines.append("")
        lines.append("| Name | Path | Relationship |")
        lines.append("|------|------|-------------|")
        for repo in data.companion_repos:
            lines.append(f"| {repo['name']} | `{repo['path']}` | {repo['relationship']} |")
        lines.append("")

    # Running Processes
    if data.running_processes:
        lines.append("## Running Processes")
        lines.append("")
        lines.append("```")
        for proc in data.running_processes:
            lines.append(proc)
        lines.append("```")
        lines.append("")

    # Agent Inbox
    if data.inbox_messages:
        lines.append("## Pending Agent Messages")
        lines.append("")
        for msg in data.inbox_messages:
            lines.append(f"- {msg}")
        lines.append("")

    # Current State
    lines.append("## Current State")
    lines.append("")
    if data.current_state:
        lines.append(data.current_state)
    if data.files_modified:
        lines.append("")
        lines.append("### Files Modified")
        lines.append("")
        lines.append("```")
        for f in data.files_modified[:30]:  # Limit to 30 files
            lines.append(f)
        if len(data.files_modified) > 30:
            lines.append(f"... and {len(data.files_modified) - 30} more")
        lines.append("```")
    lines.append("")

    # Decisions Made
    if data.decisions_made:
        lines.append("## Decisions Made")
        lines.append("")
        for i, decision in enumerate(data.decisions_made, 1):
            lines.append(f"{i}. {decision}")
        lines.append("")

    # Research Conducted
    if data.research_conducted:
        lines.append("## Research Conducted")
        lines.append("")
        lines.append(data.research_conducted)
        lines.append("")

    # Lessons Learned
    if data.lessons_learned:
        lines.append("## Lessons Learned")
        lines.append("")
        for i, lesson in enumerate(data.lessons_learned, 1):
            lines.append(f"{i}. {lesson}")
        lines.append("")

    # Known Issues
    if data.known_issues:
        lines.append("## Known Issues / Gaps")
        lines.append("")
        for issue in data.known_issues:
            lines.append(f"- [ ] {issue}")
        lines.append("")

    # Assessment (code health)
    if data.assessment:
        lines.append("## Assessment")
        lines.append("")
        for issue in data.assessment:
            lines.append(f"- {issue}")
        lines.append("")

    # Open Questions
    if data.open_questions:
        lines.append("## Open Questions")
        lines.append("")
        for q in data.open_questions:
            lines.append(f"- {q}")
        lines.append("")

    # Next Steps
    has_next_steps = data.next_steps_immediate or data.next_steps_nearterm or data.next_steps_longterm
    if has_next_steps:
        lines.append("## Next Steps")
        lines.append("")

        if data.next_steps_immediate:
            lines.append("### Immediate")
            lines.append("")
            for step in data.next_steps_immediate:
                lines.append(f"- [ ] {step}")
            lines.append("")

        if data.next_steps_nearterm:
            lines.append("### Near-Term")
            lines.append("")
            for step in data.next_steps_nearterm:
                lines.append(f"- [ ] {step}")
            lines.append("")

        if data.next_steps_longterm:
            lines.append("### Long-Term")
            lines.append("")
            for step in data.next_steps_longterm:
                lines.append(f"- [ ] {step}")
            lines.append("")

    # How to Continue
    if data.how_to_continue:
        lines.append("## How to Continue")
        lines.append("")
        lines.append(data.how_to_continue)
        lines.append("")

    # Git Information
    if include_git and (data.git_status or data.recent_commits):
        lines.append("---")
        lines.append("")
        lines.append("## Git State")
        lines.append("")

        if data.git_status:
            lines.append("### Uncommitted Changes")
            lines.append("")
            status_lines = data.git_status.split("\n")
            lines.append("```")
            if len(status_lines) > 30:
                for sl in status_lines[:25]:
                    lines.append(sl)
                lines.append(f"... and {len(status_lines) - 25} more files")
            else:
                lines.append(data.git_status)
            lines.append("```")
            lines.append("")

        if data.recent_commits:
            lines.append("### Recent Commits")
            lines.append("")
            lines.append("```")
            lines.append(data.recent_commits)
            lines.append("```")
            lines.append("")

    # Architecture Diagram
    if data.architecture_diagram:
        lines.append("## Architecture")
        lines.append("")
        lines.append(data.architecture_diagram)
        lines.append("")

    # Key Code Snippets
    if data.key_code_snippets:
        lines.append("## Key Code Snippets")
        lines.append("")
        for snippet in data.key_code_snippets:
            lines.append(f"**{snippet.get('file', 'unknown')}** - {snippet.get('marker', '')}")
            lines.append("```")
            lines.append(snippet.get('content', ''))
            lines.append("```")
            lines.append("")

    # Test Coverage
    if data.test_coverage:
        lines.append("## Test Status")
        lines.append("")
        if data.test_coverage.get("details"):
            lines.append(f"- {data.test_coverage['details']}")
        if data.test_coverage.get("sanity_checks"):
            lines.append("")
            lines.append("### Sanity Checks")
            lines.append("")
            for check in data.test_coverage["sanity_checks"]:
                lines.append(f"- {check}")
        lines.append("")

    # Performance Notes
    if data.performance_notes:
        lines.append("## Performance Notes")
        lines.append("")
        lines.append(data.performance_notes)
        lines.append("")

    # Dependency Graph
    if data.dependency_graph:
        lines.append("## Skill Dependencies")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph LR")
        seen = set()
        for dep in data.dependency_graph[:20]:  # Limit
            edge = f"    {dep['skill']} --> {dep['depends_on']}"
            if edge not in seen:
                seen.add(edge)
                lines.append(edge)
        lines.append("```")
        lines.append("")

    # Error Log Summary
    if data.error_log_summary:
        lines.append("## Recent Errors")
        lines.append("")
        lines.append("```")
        for err in data.error_log_summary[-10:]:
            lines.append(err[:200])  # Truncate long lines
        lines.append("```")
        lines.append("")

    # Environment Snapshot
    if data.environment_snapshot:
        lines.append("## Environment")
        lines.append("")
        lines.append("| Variable | Value |")
        lines.append("|----------|-------|")
        for var, val in sorted(data.environment_snapshot.items()):
            lines.append(f"| `{var}` | `{val}` |")
        lines.append("")

    # Session Transcript
    if data.session_transcript_path:
        lines.append("## Session Transcript")
        lines.append("")
        lines.append(f"Full conversation history: `{data.session_transcript_path}`")
        lines.append("")

    # Project Memory
    if data.memory_content:
        lines.append("## Project Memory")
        lines.append("")
        lines.append(data.memory_content)
        lines.append("")

    # Related Skills
    if data.related_skills:
        lines.append("## Related Skills")
        lines.append("")
        lines.append("| Skill | Relationship |")
        lines.append("|-------|-------------|")
        for skill in data.related_skills:
            lines.append(f"| `{skill}` | |")
        lines.append("")

    return "\n".join(lines)
