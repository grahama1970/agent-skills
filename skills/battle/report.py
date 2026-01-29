"""
Battle Skill - Report Generation
Generate battle reports in Markdown format.
"""
from __future__ import annotations

from datetime import datetime

from state import BattleState


def generate_report(state: BattleState) -> str:
    """Generate battle report in Markdown format."""
    winner = "Red Team" if state.red_total_score > state.blue_total_score else "Blue Team"
    margin = abs(state.red_total_score - state.blue_total_score)

    report = f"""# Battle Report: {state.battle_id}

## Executive Summary

**Winner: {winner}** (margin: {margin:.1f} points)

| Metric | Value |
|--------|-------|
| Total Rounds | {state.current_round} |
| Red Team Score | {state.red_total_score:.1f} |
| Blue Team Score | {state.blue_total_score:.1f} |
| TDSR (True Defense Success Rate) | {state.tdsr:.1%} |
| FDSR (Fake Defense Success Rate) | {state.fdsr:.1%} |
| ASC (Attack Success Count) | {state.asc} |

## Battle Timeline

| Started | Completed | Duration |
|---------|-----------|----------|
| {state.started_at or 'N/A'} | {state.completed_at or 'N/A'} | {state.current_round} rounds |

## Vulnerability Summary

Total Vulnerabilities Found: {len(state.all_findings)}
Total Patches Generated: {len(state.all_patches)}
Verified Patches: {len([p for p in state.all_patches if p.verified])}

### By Severity

| Severity | Count |
|----------|-------|
| Critical | {len([f for f in state.all_findings if f.severity == 'critical'])} |
| High | {len([f for f in state.all_findings if f.severity == 'high'])} |
| Medium | {len([f for f in state.all_findings if f.severity == 'medium'])} |
| Low | {len([f for f in state.all_findings if f.severity == 'low'])} |

## Round-by-Round Summary

| Round | Red Findings | Blue Patches | Red Score | Blue Score |
|-------|--------------|--------------|-----------|------------|
"""

    for r in state.rounds[:20]:
        report += f"| {r.round_number} | {len(r.red_findings)} | {len(r.blue_patches)} | {r.red_score:.1f} | {r.blue_score:.1f} |\n"

    if len(state.rounds) > 20:
        report += f"| ... | ({len(state.rounds) - 20} more rounds) | ... | ... | ... |\n"

    # Recommendations based on results
    if state.red_total_score > state.blue_total_score:
        rec1 = "**Improve defenses** - Red team dominated, consider security hardening"
        rec3 = "Run another battle after implementing fixes"
    else:
        rec1 = "**Maintain defensive posture** - Blue team successfully defended most attacks"
        rec3 = "Consider expanding attack surface for Red team"

    focus_area = state.all_findings[0].type.value if state.all_findings else "N/A"

    report += f"""

## Recommendations

1. {rec1}

2. **Focus Areas**: Based on findings, prioritize fixes for {focus_area} vulnerabilities

3. **Next Steps**: {rec3}

---
Generated: {datetime.now().isoformat()}
"""

    return report


def generate_summary(state: BattleState) -> str:
    """Generate a brief battle summary."""
    winner = "Red Team" if state.red_total_score > state.blue_total_score else "Blue Team"
    margin = abs(state.red_total_score - state.blue_total_score)

    return (
        f"Battle {state.battle_id}: {winner} wins by {margin:.1f} points. "
        f"Rounds: {state.current_round}, Findings: {len(state.all_findings)}, "
        f"Patches: {len([p for p in state.all_patches if p.verified])}"
    )
