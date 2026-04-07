"""
All public symbols for the create-figure package.

Imported by __init__.py so that `from create_figure import X` continues
to work.  This module owns the per-symbol re-export list; __init__.py is
kept thin (≤20 non-blank non-comment lines).
"""

# --- Config ---
from config import (  # noqa: F401
    IEEE_SINGLE_COLUMN,
    IEEE_DOUBLE_COLUMN,
    IEEE_FIGURE_SIZES,
    IEEE_RC_PARAMS,
    COLORBLIND_SAFE_CMAPS,
    PROBLEMATIC_CMAPS,
    DOMAIN_GROUPS,
    DATA_TYPE_RECOMMENDATIONS,
    LEAN4_PROVE_SCRIPT,
)

# --- Utilities ---
from utils import (  # noqa: F401
    check_graphviz,
    check_mermaid,
    check_matplotlib,
    check_seaborn,
    check_plotly,
    check_networkx,
    check_pandas,
    check_squarify,
    check_scipy,
    check_control,
    check_pydeps,
    check_pyreverse,
    check_numpy,
    apply_ieee_style,
    check_colormap_accessibility,
    get_numpy,
)

# --- Validation ---
from validation import (  # noqa: F401
    ValidationError,
    validate_json_file,
    validate_scaling_data,
    validate_metrics_data,
    validate_flow_data,
    validate_heatmap_data,
    validate_network_data,
    validate_output_path,
    create_validation_error_message,
)

# --- Graphviz Backend ---
from graphviz_backend import (  # noqa: F401
    generate_dependency_graph,
    generate_class_diagram,
)

# --- Mermaid Backend ---
from mermaid_backend import (  # noqa: F401
    generate_mermaid_dep_graph,
    generate_mermaid_architecture,
    generate_mermaid_workflow,
    render_mermaid,
)

# --- NetworkX Backend ---
from networkx_backend import (  # noqa: F401
    generate_force_directed,
)

# --- Matplotlib Backend ---
from matplotlib_backend import (  # noqa: F401
    generate_metrics_chart,
    generate_heatmap,
    generate_radar_chart,
    generate_latex_table,
)

# --- Plotly Backend ---
from plotly_backend import (  # noqa: F401
    generate_sankey_diagram,
    generate_treemap,
    generate_sunburst,
    generate_parallel_coordinates,
)

# --- Control Systems ---
from control_systems import (  # noqa: F401
    generate_bode_plot,
    generate_nyquist_plot,
    generate_root_locus,
    generate_pole_zero_map,
)

# --- ML Visualizations ---
from ml_visualizations import (  # noqa: F401
    generate_confusion_matrix,
    generate_roc_curve,
    generate_precision_recall,
    generate_training_curves,
    generate_attention_heatmap,
    generate_embedding_scatter,
    generate_scaling_law_plot,
    generate_roofline_plot,
    generate_throughput_latency,
    generate_feature_importance,
    generate_calibration_plot,
)

# --- Bio Visualizations (also available via ml_visualizations) ---
from bio_visualizations import (  # noqa: F401
    generate_violin_plot,
    generate_volcano_plot,
    generate_survival_curve,
    generate_manhattan_plot,
)

# --- Analysis ---
from analysis import (  # noqa: F401
    generate_architecture_diagram,
    generate_workflow_diagram,
    generate_lean4_theorem_figure,
    generate_from_assess,
)

# --- CLI Utilities ---
from cli_utils import register_utility_commands  # noqa: F401

__all__ = [
    # config
    "IEEE_SINGLE_COLUMN",
    "IEEE_DOUBLE_COLUMN",
    "IEEE_FIGURE_SIZES",
    "IEEE_RC_PARAMS",
    "COLORBLIND_SAFE_CMAPS",
    "PROBLEMATIC_CMAPS",
    "DOMAIN_GROUPS",
    "DATA_TYPE_RECOMMENDATIONS",
    "LEAN4_PROVE_SCRIPT",
    # utils
    "check_graphviz",
    "check_mermaid",
    "check_matplotlib",
    "check_seaborn",
    "check_plotly",
    "check_networkx",
    "check_pandas",
    "check_squarify",
    "check_scipy",
    "check_control",
    "check_pydeps",
    "check_pyreverse",
    "check_numpy",
    "apply_ieee_style",
    "check_colormap_accessibility",
    "get_numpy",
    # validation
    "ValidationError",
    "validate_json_file",
    "validate_scaling_data",
    "validate_metrics_data",
    "validate_flow_data",
    "validate_heatmap_data",
    "validate_network_data",
    "validate_output_path",
    "create_validation_error_message",
    # graphviz
    "generate_dependency_graph",
    "generate_class_diagram",
    # mermaid
    "generate_mermaid_dep_graph",
    "generate_mermaid_architecture",
    "generate_mermaid_workflow",
    "render_mermaid",
    # networkx
    "generate_force_directed",
    # matplotlib
    "generate_metrics_chart",
    "generate_heatmap",
    "generate_radar_chart",
    "generate_latex_table",
    # plotly
    "generate_sankey_diagram",
    "generate_treemap",
    "generate_sunburst",
    "generate_parallel_coordinates",
    # control systems
    "generate_bode_plot",
    "generate_nyquist_plot",
    "generate_root_locus",
    "generate_pole_zero_map",
    # ml
    "generate_confusion_matrix",
    "generate_roc_curve",
    "generate_precision_recall",
    "generate_training_curves",
    "generate_attention_heatmap",
    "generate_embedding_scatter",
    "generate_scaling_law_plot",
    "generate_roofline_plot",
    "generate_throughput_latency",
    "generate_feature_importance",
    "generate_calibration_plot",
    # bio
    "generate_violin_plot",
    "generate_volcano_plot",
    "generate_survival_curve",
    "generate_manhattan_plot",
    # analysis
    "generate_architecture_diagram",
    "generate_workflow_diagram",
    "generate_lean4_theorem_figure",
    "generate_from_assess",
    # cli
    "register_utility_commands",
]
