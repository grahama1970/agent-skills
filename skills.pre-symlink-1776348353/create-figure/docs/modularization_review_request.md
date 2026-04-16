# Code Review Request: fixture-graph Modularization

## Summary

This PR modularizes the fixture-graph skill from a 5397-line monolith into 12 focused, debuggable modules:

| Module | Lines | Purpose |
|--------|-------|---------|
| config.py | 175 | Constants, IEEE settings, domain groups |
| utils.py | 193 | Backend checks, style utilities |
| validation.py | 371 | Input validation framework |
| graphviz_backend.py | 323 | DOT/Graphviz rendering |
| mermaid_backend.py | 140 | Mermaid diagram generation |
| networkx_backend.py | 249 | NetworkX/D3 visualizations |
| matplotlib_backend.py | 775 | Core matplotlib plots |
| plotly_backend.py | 394 | Interactive Plotly charts |
| control_systems.py | 576 | Control/aerospace visualizations |
| ml_visualizations.py | 943 | ML/LLM evaluation plots |
| analysis.py | 217 | Code analysis and architecture diagrams |
| fixture_graph.py | 857 | Thin CLI entry point |

**Total: 5213 lines** (was 5397 in monolith)

## Changes Made

1. **Created config.py** - Centralized constants:
   - IEEE publication settings (IEEE_RC_PARAMS, IEEE_SINGLE_COLUMN, etc.)
   - Domain groups for visualization discovery
   - Data type recommendations
   - FigureConfig and DependencyNode dataclasses

2. **Created utils.py** - Common utilities:
   - Backend availability checks (check_matplotlib, check_graphviz, etc.)
   - IEEE style application
   - Colormap accessibility warnings

3. **Created graphviz_backend.py** - Graphviz rendering:
   - render_graphviz() - Core DOT rendering
   - generate_dependency_graph() - Python project dependencies
   - generate_class_diagram() - UML via pyreverse
   - generate_graphviz_architecture() - Architecture diagrams

4. **Created mermaid_backend.py** - Mermaid diagrams:
   - render_mermaid() - Core Mermaid rendering
   - generate_mermaid_dep_graph() - Dependency graphs
   - generate_mermaid_architecture() - Architecture diagrams
   - generate_mermaid_workflow() - Workflow diagrams

5. **Created networkx_backend.py** - NetworkX visualizations:
   - generate_force_directed() - Force-directed graphs
   - generate_pert_network() - PERT diagrams
   - networkx_to_d3_json() - D3.js export

6. **Created matplotlib_backend.py** - Core matplotlib:
   - Metrics charts (bar, pie, line, hbar)
   - Heatmaps
   - Radar/spider charts
   - Polar plots
   - Contour plots
   - Vector fields
   - Phase portraits
   - Gantt charts
   - 3D surface/contour plots
   - Complex plane visualization
   - LaTeX table generation

7. **Created plotly_backend.py** - Plotly charts:
   - Sankey diagrams (with matplotlib fallback)
   - Sunburst charts
   - Treemaps (with squarify fallback)
   - Parallel coordinates

8. **Created control_systems.py** - Control visualizations:
   - Bode plots (python-control or scipy)
   - Nyquist plots
   - Root locus plots
   - Pole-zero maps
   - State-space visualization
   - Spectrograms
   - Filter response

9. **Created ml_visualizations.py** - ML/LLM plots:
   - Confusion matrices
   - ROC curves
   - Precision-recall curves
   - Training curves
   - Attention heatmaps
   - Embedding scatter (t-SNE/UMAP)
   - Scaling law plots
   - Roofline plots
   - Throughput vs latency
   - Violin plots
   - Volcano plots
   - Survival curves
   - Manhattan plots
   - Feature importance
   - Calibration plots

10. **Created analysis.py** - High-level orchestration:
    - generate_architecture_diagram()
    - generate_workflow_diagram()
    - generate_lean4_theorem_figure()
    - generate_from_assess()

11. **Refactored fixture_graph.py** - Thin CLI:
    - Just CLI command definitions
    - All logic delegated to backend modules
    - Clean imports from modular structure

12. **Updated tests** - Fixed imports to use new module structure

13. **Updated sanity.sh** - Comprehensive modular testing:
    - Module import tests
    - CLI command tests
    - Module size validation
    - Pytest integration

## Quality Gates Verified

- [x] All modules import correctly (sanity.sh passes)
- [x] CLI loads and all commands work
- [x] 60 tests pass, 14 skipped (3D tests need matplotlib 3D support)
- [x] No circular imports (verified by module import tests)
- [x] Original preserved as fixture_graph_monolith.py

## Files for Review

Please review these files in the following order:

1. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/config.py`
2. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/utils.py`
3. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/graphviz_backend.py`
4. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/mermaid_backend.py`
5. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/networkx_backend.py`
6. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/matplotlib_backend.py`
7. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/plotly_backend.py`
8. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/control_systems.py`
9. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/ml_visualizations.py`
10. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/analysis.py`
11. `/home/graham/workspace/experiments/pi-mono/.pi/skills/fixture-graph/fixture_graph.py`

## Review Focus Areas

1. **Import consistency** - Are absolute imports used correctly?
2. **Error handling** - Are errors propagated properly?
3. **Code duplication** - Any patterns that could be further consolidated?
4. **Type hints** - Are return types and parameters properly annotated?
5. **Docstrings** - Are all public functions documented?
6. **Edge cases** - Are boundary conditions handled?
