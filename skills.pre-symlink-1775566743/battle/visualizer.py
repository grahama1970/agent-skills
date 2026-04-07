"""
Battle Skill - Visualizer Bridge
Converts BattleState into interactive D3.js and Plotly data structures.
"""
import os
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from state import BattleState, Finding, Patch, AttackType, DefenseType
from config import REPORTS_DIR

def findings_to_sunburst_data(state: BattleState) -> Dict[str, Any]:
    """
    Convert all findings into a Sunburst hierarchical structure.
    Hierarchy: Root -> Tactic (type) -> Severity -> Findings
    """
    root = {"name": "Battle Findings", "children": []}
    tactics_map = {}

    for finding in state.all_findings:
        tactic = finding.type.value
        if tactic not in tactics_map:
            tactics_map[tactic] = {"name": tactic, "children": {}}
            root["children"].append(tactics_map[tactic])
        
        severity = finding.severity
        if severity not in tactics_map[tactic]["children"]:
            tactics_map[tactic]["children"][severity] = {"name": severity, "children": []}
        
        tactics_map[tactic]["children"][severity]["children"].append({
            "name": finding.id,
            "value": 1,
            "description": finding.description[:100],
            "severity": finding.severity
        })

    # Cleanup: convert dict children to lists
    for tactic_name, tactic_data in tactics_map.items():
        tactic_data["children"] = list(tactic_data["children"].values())

    return root

def battle_to_sankey_data(state: BattleState) -> Dict[str, Any]:
    """
    Convert battle history into a Sankey flow across stages.
    Stages: Attacks -> Success/Failure -> Patches -> Verified/Broken
    """
    nodes = [
        {"name": "Total Attacks"},
        {"name": "Found Vulnerabilities"},
        {"name": "No Findings"},
        {"name": "Patches Generated"},
        {"name": "Successful Patches"},
        {"name": "Failed/Broken Patches"}
    ]
    
    links = []
    
    total_attacks = len(state.rounds)
    found_vulns = len(state.all_findings)
    no_finds = max(0, total_attacks - found_vulns)
    
    patches_gen = len(state.all_patches)
    success_patches = len([p for p in state.all_patches if p.verified])
    failed_patches = max(0, patches_gen - success_patches)

    # 0: Total -> 1: Found
    links.append({"source": 0, "target": 1, "value": found_vulns})
    # 0: Total -> 2: None
    links.append({"source": 0, "target": 2, "value": no_finds})
    
    # 1: Found -> 3: Patches
    links.append({"source": 1, "target": 3, "value": patches_gen})
    
    # 3: Patches -> 4: Success
    links.append({"source": 3, "target": 4, "value": success_patches})
    # 3: Patches -> 5: Failed
    links.append({"source": 3, "target": 5, "value": failed_patches})

    return {"nodes": nodes, "links": links}

def timeline_to_graph_data(state: BattleState) -> Dict[str, Any]:
    """
    Convert battle timeline into a force-directed graph.
    """
    nodes = []
    links = []
    
    for r in state.rounds:
        round_node = f"round_{r.round_number}"
        nodes.append({"id": round_node, "group": 1, "label": f"Round {r.round_number}"})
        
        for f in r.red_findings:
            nodes.append({"id": f.id, "group": 2, "label": f.type.value, "severity": f.severity})
            links.append({"source": round_node, "target": f.id})
            
        for p in r.blue_patches:
            nodes.append({"id": p.id, "group": 3, "label": "Patch", "verified": p.verified})
            links.append({"source": p.finding_id, "target": p.id})

    return {"nodes": nodes, "links": links}

def generate_interactive_report(state: BattleState) -> Path:
    """
    Generate the data artifacts for create-figure.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    base_path = REPORTS_DIR / f"{state.battle_id}_viz"
    base_path.mkdir(parents=True, exist_ok=True)
    
    sunburst_data = findings_to_sunburst_data(state)
    sankey_data = battle_to_sankey_data(state)
    graph_data = timeline_to_graph_data(state)
    
    (base_path / "sunburst.json").write_text(json.dumps(sunburst_data, indent=2))
    (base_path / "sankey.json").write_text(json.dumps(sankey_data, indent=2))
    (base_path / "timeline.json").write_text(json.dumps(graph_data, indent=2))
    
    return base_path

def generate_visualizations(state: BattleState) -> Path:
    """
    Generate all interactive visualizations and return the directory path.
    """
    base_path = generate_interactive_report(state)
    create_figure_script = Path(__file__).parent.parent / "create-figure" / "run.sh"
    
    if not create_figure_script.exists():
        return base_path

    # Generate Sankey
    subprocess.run([
        str(create_figure_script), "sankey",
        "--input", str(base_path / "sankey.json"),
        "--output", str(base_path / "sankey.html"),
        "--format", "html",
        "--title", "Attack Flow: Recon to Exfiltration"
    ], capture_output=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    # Generate Sunburst
    subprocess.run([
        str(create_figure_script), "sunburst",
        "--input", str(base_path / "sunburst.json"),
        "--output", str(base_path / "sunburst.html"),
        "--format", "html",
        "--title", "Tactical Risk Matrix"
    ], capture_output=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    # Generate Force Graph (Timeline)
    subprocess.run([
        str(create_figure_script), "force-graph",
        "--input", str(base_path / "timeline.json"),
        "--output", str(base_path / "timeline.html"),
        "--format", "json", # Still produces JSON for custom D3 if needed, but create-figure can render it
        "--title", "Battle Timeline Graph"
    ], capture_output=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    return base_path
