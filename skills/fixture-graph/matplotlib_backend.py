#!/usr/bin/env python3
"""
Matplotlib backend for fixture-graph skill.

Handles core matplotlib visualizations:
- Metrics charts (bar, hbar, pie, line)
- Heatmaps
- Radar charts
- Polar plots
- Contour plots
- Vector fields
- Phase portraits
- Gantt charts
- 3D plots
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer

from config import IEEE_SINGLE_COLUMN, IEEE_DOUBLE_COLUMN
from utils import check_matplotlib, check_seaborn, check_pandas, apply_ieee_style, get_numpy


def generate_metrics_chart(
    title: str,
    data: Dict[str, float],
    output_path: Path,
    chart_type: str = "bar",
    format: str = "pdf",
    figsize: Optional[Tuple[float, float]] = None,
) -> bool:
    """
    Generate publication-quality metrics chart using Seaborn (preferred) or matplotlib.

    Args:
        title: Chart title
        data: Dictionary of label -> value
        output_path: Output file path
        chart_type: bar, hbar, pie, line
        format: Output format (pdf, png, svg)
        figsize: Optional (width, height) in inches

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib not available", err=True)
        return False

    import matplotlib.pyplot as plt
    np = get_numpy()
    import numpy as np_real
    apply_ieee_style()

    # Use seaborn for better aesthetics if available
    use_seaborn = check_seaborn()
    if use_seaborn:
        import seaborn as sns
        # Set publication-quality seaborn theme
        sns.set_theme(style="whitegrid", context="paper", font_scale=0.9)
        sns.set_palette("Blues_d")

    if figsize is None:
        figsize = (IEEE_SINGLE_COLUMN, 2.5)

    fig, ax = plt.subplots(figsize=figsize)

    labels = list(data.keys())
    values = list(data.values())

    if use_seaborn and chart_type in ("bar", "hbar"):
        import pandas as pd
        df = pd.DataFrame({"Label": labels, "Value": values})

        if chart_type == "bar":
            sns.barplot(data=df, x="Label", y="Value", ax=ax, hue="Label",
                       palette="Blues_d", edgecolor="black", legend=False)
            ax.set_ylabel("Value")
            ax.set_xlabel("")
            # Add value labels on bars
            for i, (_, val) in enumerate(zip(labels, values)):
                ax.annotate(f'{val:.1f}' if isinstance(val, float) else str(val),
                           xy=(i, val),
                           xytext=(0, 3), textcoords="offset points",
                           ha='center', va='bottom', fontsize=7)
        else:  # hbar
            sns.barplot(data=df, x="Value", y="Label", ax=ax, hue="Label",
                       palette="Blues_d", edgecolor="black", orient="h", legend=False)
            ax.set_xlabel("Value")
            ax.set_ylabel("")

    elif use_seaborn and chart_type == "line":
        import pandas as pd
        df = pd.DataFrame({"Label": labels, "Value": values})
        sns.lineplot(data=df, x="Label", y="Value", ax=ax, marker="o",
                    color="steelblue", linewidth=2, markersize=8)
        ax.set_ylabel("Value")
        ax.set_xlabel("")

    else:
        # Fallback to matplotlib for pie charts or when seaborn unavailable
        colors = plt.cm.Blues(np_real.linspace(0.4, 0.8, len(labels))) if len(labels) > 1 else ["steelblue"]

        if chart_type == "bar":
            bars = ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.5)
            ax.set_ylabel("Value")
            for bar, val in zip(bars, values):
                height = bar.get_height()
                ax.annotate(f'{val:.1f}' if isinstance(val, float) else str(val),
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 2), textcoords="offset points",
                           ha='center', va='bottom', fontsize=6)

        elif chart_type == "hbar":
            bars = ax.barh(labels, values, color=colors, edgecolor="black", linewidth=0.5)
            ax.set_xlabel("Value")

        elif chart_type == "pie":
            ax.pie(values, labels=labels, autopct="%1.1f%%",
                   colors=colors, wedgeprops={"edgecolor": "black", "linewidth": 0.5})

        elif chart_type == "line":
            ax.plot(labels, values, marker="o", color="steelblue",
                    markeredgecolor="black", markeredgewidth=0.5)
            ax.set_ylabel("Value")

        else:
            ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.5)

    if chart_type != "pie":
        ax.set_title(title, fontweight="bold", fontsize=9)
        plt.xticks(rotation=45, ha="right")

    # Remove seaborn's grid for cleaner look in publications
    if use_seaborn:
        ax.grid(True, axis='y', alpha=0.3)
        sns.despine(ax=ax)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_heatmap(
    data: Dict[str, Dict[str, float]],
    output_path: Path,
    title: str = "Heatmap",
    format: str = "pdf",
    cmap: str = "Blues",
) -> bool:
    """
    Generate heatmap for field distributions or correlation matrices.

    Args:
        data: Nested dict {row_label: {col_label: value}}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        cmap: Colormap name

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib not available for heatmap", err=True)
        return False

    import matplotlib.pyplot as plt
    apply_ieee_style()

    # Convert to 2D array
    row_labels = list(data.keys())
    col_labels = list(data[row_labels[0]].keys()) if row_labels else []
    matrix = [[data[r].get(c, 0) for c in col_labels] for r in row_labels]

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    if check_seaborn():
        import seaborn as sns
        import pandas as pd
        df = pd.DataFrame(matrix, index=row_labels, columns=col_labels)
        sns.heatmap(df, ax=ax, cmap=cmap, annot=True, fmt=".1f",
                   linewidths=0.5, cbar_kws={"shrink": 0.8})
    else:
        im = ax.imshow(matrix, cmap=cmap, aspect='auto')
        ax.set_xticks(range(len(col_labels)))
        ax.set_yticks(range(len(row_labels)))
        ax.set_xticklabels(col_labels, rotation=45, ha='right')
        ax.set_yticklabels(row_labels)
        plt.colorbar(im, ax=ax, shrink=0.8)

    ax.set_title(title, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_radar_chart(
    data: Dict[str, Dict[str, float]],
    output_path: Path,
    title: str = "Radar Chart",
    format: str = "pdf",
) -> bool:
    """
    Generate radar/spider chart for multi-attribute comparison.

    Args:
        data: Dict of {series_name: {dimension: value}}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for radar chart", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    # Get dimensions from first series
    first_series = list(data.values())[0]
    dimensions = list(first_series.keys())
    num_dims = len(dimensions)

    # Calculate angles for each axis
    angles = [n / float(num_dims) * 2 * 3.14159 for n in range(num_dims)]
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN),
                          subplot_kw=dict(polar=True))

    colors = plt.cm.Set2(np.linspace(0, 1, len(data)))

    for i, (series_name, values_dict) in enumerate(data.items()):
        values = [values_dict.get(d, 0) for d in dimensions]
        values += values[:1]  # Close the polygon

        ax.plot(angles, values, 'o-', linewidth=1.5, label=series_name, color=colors[i])
        ax.fill(angles, values, alpha=0.25, color=colors[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dimensions, fontsize=7)
    ax.set_title(title, fontweight="bold", y=1.08)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0), fontsize=7)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_polar_plot(
    theta: List[float],
    r: List[float],
    output_path: Path,
    title: str = "Polar Plot",
    format: str = "pdf",
) -> bool:
    """
    Generate polar coordinate plot.

    Args:
        theta: Angles in radians
        r: Radii
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for polar plot", err=True)
        return False

    import matplotlib.pyplot as plt
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN),
                          subplot_kw=dict(polar=True))

    ax.plot(theta, r, 'b-', linewidth=1.5)
    ax.fill(theta, r, alpha=0.25, color='steelblue')
    ax.set_title(title, fontweight="bold", y=1.08)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_contour_plot(
    x: List[float],
    y: List[float],
    z: List[List[float]],
    output_path: Path,
    title: str = "Contour Plot",
    format: str = "pdf",
    levels: int = 15,
    cmap: str = "viridis",
    filled: bool = True,
) -> bool:
    """
    Generate contour plot for field distributions (flux, temperature, stress).

    Args:
        x: X coordinates
        y: Y coordinates
        z: 2D array of values z[y_idx][x_idx]
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        levels: Number of contour levels
        cmap: Colormap name
        filled: Use filled contours

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for contour plot", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    X, Y = np.meshgrid(x, y)
    Z = np.array(z)

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    if filled:
        cs = ax.contourf(X, Y, Z, levels=levels, cmap=cmap)
    else:
        cs = ax.contour(X, Y, Z, levels=levels, cmap=cmap)

    plt.colorbar(cs, ax=ax, shrink=0.8)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_title(title, fontweight="bold")
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_vector_field(
    x: List[float],
    y: List[float],
    u: List[List[float]],
    v: List[List[float]],
    output_path: Path,
    title: str = "Vector Field",
    format: str = "pdf",
    streamlines: bool = False,
) -> bool:
    """
    Generate vector field plot (flow fields, gradients).

    Args:
        x: X coordinates
        y: Y coordinates
        u: X-components of vectors u[y_idx][x_idx]
        v: Y-components of vectors v[y_idx][x_idx]
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        streamlines: Show streamlines instead of quiver

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for vector field", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    X, Y = np.meshgrid(x, y)
    U = np.array(u)
    V = np.array(v)

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    if streamlines:
        speed = np.sqrt(U**2 + V**2)
        ax.streamplot(X, Y, U, V, color=speed, cmap='Blues', density=1.5,
                     linewidth=1, arrowsize=1)
    else:
        magnitude = np.sqrt(U**2 + V**2)
        ax.quiver(X, Y, U, V, magnitude, cmap='Blues', scale=20)

    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_title(title, fontweight="bold")
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_phase_portrait(
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
    dx_dy_func: str,
    output_path: Path,
    title: str = "Phase Portrait",
    format: str = "pdf",
    grid_size: int = 20,
) -> bool:
    """
    Generate phase portrait for dynamical systems (differential equations).

    Args:
        x_range: (x_min, x_max)
        y_range: (y_min, y_max)
        dx_dy_func: String defining dx/dt and dy/dt as Python expressions
                   e.g., "dx = y; dy = -x - 0.5*y"
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        grid_size: Number of points per axis

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for phase portrait", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    # Parse the dx/dy expressions
    try:
        parts = dx_dy_func.replace(' ', '').split(';')
        dx_expr = parts[0].split('=')[1]
        dy_expr = parts[1].split('=')[1]
    except (IndexError, ValueError):
        typer.echo("[ERROR] Invalid dx_dy_func format. Use: 'dx = y; dy = -x'", err=True)
        return False

    x = np.linspace(x_range[0], x_range[1], grid_size)
    y = np.linspace(y_range[0], y_range[1], grid_size)
    X, Y = np.meshgrid(x, y)

    # Evaluate vector field (SAFE: only allow numpy math)
    try:
        safe_dict = {"x": X, "y": Y, "np": np, "sin": np.sin, "cos": np.cos,
                    "exp": np.exp, "sqrt": np.sqrt, "abs": np.abs}
        DX = eval(dx_expr, {"__builtins__": {}}, safe_dict)
        DY = eval(dy_expr, {"__builtins__": {}}, safe_dict)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to evaluate expressions: {e}", err=True)
        return False

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Streamplot for phase portrait
    speed = np.sqrt(DX**2 + DY**2)
    ax.streamplot(X, Y, DX, DY, color=speed, cmap='Blues', density=1.5,
                 linewidth=1, arrowsize=1)

    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_title(title, fontweight="bold")
    ax.set_xlim(x_range)
    ax.set_ylim(y_range)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_gantt_chart(
    tasks: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Project Schedule",
    format: str = "pdf",
) -> bool:
    """
    Generate Gantt chart for project scheduling.

    Args:
        tasks: List of {name, start, duration, color?} dicts
               start and duration are numeric (e.g., days)
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for Gantt chart", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, len(tasks) * 0.4 + 1))

    colors = plt.cm.Set3(np.linspace(0, 1, len(tasks)))

    for i, task in enumerate(tasks):
        name = task.get('name', f'Task {i+1}')
        start = task.get('start', 0)
        duration = task.get('duration', 1)
        color = task.get('color', colors[i])

        ax.barh(i, duration, left=start, height=0.6, color=color,
               edgecolor='black', linewidth=0.5)
        ax.text(start + duration/2, i, name, ha='center', va='center', fontsize=7)

    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([])
    ax.set_xlabel('Time')
    ax.set_title(title, fontweight="bold")
    ax.invert_yaxis()  # Tasks read top-to-bottom
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_3d_surface(
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
    z_function: str,
    output_path: Path,
    title: str = "3D Surface",
    format: str = "pdf",
    resolution: int = 50,
    colormap: str = "viridis",
    view_angle: Tuple[float, float] = (30, 45),
) -> bool:
    """Generate 3D surface plot for multivariate mathematical functions."""
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for 3D surface plot", err=True)
        return False

    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
        import numpy as np
    except ImportError as e:
        typer.echo(f"[ERROR] 3D plotting unavailable: {e}", err=True)
        return False

    apply_ieee_style()

    try:
        x = np.linspace(x_range[0], x_range[1], resolution)
        y = np.linspace(y_range[0], y_range[1], resolution)
        X, Y = np.meshgrid(x, y)

        # Evaluate function safely
        safe_dict = {"x": X, "y": Y, "np": np, "sin": np.sin, "cos": np.cos,
                    "exp": np.exp, "sqrt": np.sqrt, "abs": np.abs, "log": np.log,
                    "tan": np.tan, "arctan": np.arctan, "pi": np.pi}
        Z = eval(z_function, {"__builtins__": {}}, safe_dict)

        fig = plt.figure(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN * 1.2))
        ax = fig.add_subplot(111, projection='3d')

        surf = ax.plot_surface(X, Y, Z, cmap=colormap, alpha=0.8,
                              linewidth=0, antialiased=True)
        fig.colorbar(surf, shrink=0.5, aspect=5)

        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.set_title(title, fontweight="bold")
        ax.view_init(elev=view_angle[0], azim=view_angle[1])

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    except Exception as e:
        typer.echo(f"[ERROR] 3D surface computation failed: {e}", err=True)
        return False


def generate_3d_contour(
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
    z_function: str,
    output_path: Path,
    title: str = "3D Contour",
    format: str = "pdf",
    resolution: int = 50,
    levels: int = 20,
    colormap: str = "viridis",
) -> bool:
    """Generate 3D contour plot for multivariate mathematical functions."""
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for 3D contour plot", err=True)
        return False

    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
        import numpy as np
    except ImportError as e:
        typer.echo(f"[ERROR] 3D plotting unavailable: {e}", err=True)
        return False

    apply_ieee_style()

    try:
        x = np.linspace(x_range[0], x_range[1], resolution)
        y = np.linspace(y_range[0], y_range[1], resolution)
        X, Y = np.meshgrid(x, y)

        safe_dict = {"x": X, "y": Y, "np": np, "sin": np.sin, "cos": np.cos,
                    "exp": np.exp, "sqrt": np.sqrt, "abs": np.abs, "log": np.log,
                    "tan": np.tan, "arctan": np.arctan, "pi": np.pi}
        Z = eval(z_function, {"__builtins__": {}}, safe_dict)

        fig = plt.figure(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN * 1.2))
        ax = fig.add_subplot(111, projection='3d')

        contour = ax.contour3D(X, Y, Z, levels=levels, cmap=colormap)
        fig.colorbar(contour, shrink=0.5, aspect=5)

        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.set_title(title, fontweight="bold")

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    except Exception as e:
        typer.echo(f"[ERROR] 3D contour computation failed: {e}", err=True)
        return False


def generate_complex_plane(
    complex_numbers: List[complex],
    output_path: Path,
    title: str = "Complex Plane",
    format: str = "pdf",
    show_unit_circle: bool = True,
    color_by_magnitude: bool = True,
) -> bool:
    """Generate Argand diagram (complex plane visualization)."""
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for complex plane visualization", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    try:
        fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

        if not complex_numbers:
            typer.echo("[WARN] No complex numbers provided for visualization", err=True)
            return False

        real_parts = [z.real for z in complex_numbers]
        imag_parts = [z.imag for z in complex_numbers]

        if color_by_magnitude:
            magnitudes = [abs(z) for z in complex_numbers]
            scatter = ax.scatter(real_parts, imag_parts, c=magnitudes,
                               cmap='viridis', s=50, alpha=0.7)
            cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
            cbar.set_label('Magnitude', rotation=-90, va="bottom")
        else:
            ax.scatter(real_parts, imag_parts, s=50, alpha=0.7, color='blue')

        if show_unit_circle:
            theta = np.linspace(0, 2*np.pi, 100)
            ax.plot(np.cos(theta), np.sin(theta), 'k--', alpha=0.5, label='Unit Circle')
            ax.legend(fontsize=7)

        ax.set_xlabel('Real Part')
        ax.set_ylabel('Imaginary Part')
        ax.set_title(title, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal')

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    except Exception as e:
        typer.echo(f"[ERROR] Complex plane visualization failed: {e}", err=True)
        return False


def generate_latex_table(
    title: str,
    headers: List[str],
    rows: List[List[str]],
    output_path: Path,
    caption: Optional[str] = None,
    label: Optional[str] = None,
) -> bool:
    """Generate LaTeX table with proper escaping and formatting."""
    def escape_latex(text: str) -> str:
        replacements = [
            ("\\", "\\textbackslash{}"),
            ("&", "\\&"),
            ("%", "\\%"),
            ("$", "\\$"),
            ("#", "\\#"),
            ("_", "\\_"),
            ("{", "\\{"),
            ("}", "\\}"),
            ("~", "\\textasciitilde{}"),
            ("^", "\\textasciicircum{}"),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    col_spec = "|" + "|".join(["l"] * len(headers)) + "|"

    if label is None:
        label = "tab:" + title.lower().replace(" ", "_").replace("-", "_")

    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        "\\small",
        f"\\begin{{tabular}}{{{col_spec}}}",
        "\\hline",
        " & ".join(f"\\textbf{{{escape_latex(h)}}}" for h in headers) + " \\\\",
        "\\hline",
    ]

    for row in rows:
        escaped_row = [escape_latex(str(cell)) for cell in row]
        lines.append(" & ".join(escaped_row) + " \\\\")

    lines.extend([
        "\\hline",
        "\\end{tabular}",
        f"\\caption{{{escape_latex(caption or title)}}}",
        f"\\label{{{label}}}",
        "\\end{table}",
    ])

    output_path.write_text("\n".join(lines))
    return True
