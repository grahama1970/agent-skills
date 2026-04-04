#!/usr/bin/env python3
"""
Biology and biostatistics visualization module for fixture-graph skill.

Handles bio/medical visualizations:
- Violin plots (distribution comparison)
- Volcano plots (differential expression)
- Survival curves (Kaplan-Meier)
- Manhattan plots (GWAS)
"""

from pathlib import Path
from typing import Any, Dict, List

import typer

from config import IEEE_SINGLE_COLUMN, IEEE_DOUBLE_COLUMN
from utils import check_matplotlib, check_seaborn, apply_ieee_style


def generate_violin_plot(
    data: Dict[str, List[float]],
    output_path: Path,
    title: str = "Distribution Comparison",
    format: str = "pdf",
    x_label: str = "",
    y_label: str = "Value",
) -> bool:
    """
    Generate violin plot for distribution comparison.

    Args:
        data: Dict of {group: [values]}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        x_label: X-axis label
        y_label: Y-axis label

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for violin plot", err=True)
        return False

    import matplotlib.pyplot as plt
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN * 1.5, IEEE_SINGLE_COLUMN))

    if check_seaborn():
        import seaborn as sns
        import pandas as pd

        # Convert to long format for seaborn
        records = []
        for group, values in data.items():
            for v in values:
                records.append({'Group': group, 'Value': v})
        df = pd.DataFrame(records)

        sns.violinplot(data=df, x='Group', y='Value', ax=ax, palette='Blues')
    else:
        # Matplotlib fallback
        labels = list(data.keys())
        values = list(data.values())
        ax.violinplot(values, positions=range(len(labels)), showmeans=True)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right')

    if x_label:
        ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title, fontweight="bold")
    ax.grid(True, axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_volcano_plot(
    data: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Volcano Plot",
    format: str = "pdf",
    fc_threshold: float = 1.0,
    pval_threshold: float = 0.05,
) -> bool:
    """
    Generate volcano plot for differential expression analysis.

    Args:
        data: List of {gene, log2fc, pvalue} dicts
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        fc_threshold: Log2 fold change threshold
        pval_threshold: P-value threshold

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for volcano plot", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    log2fc = np.array([d['log2fc'] for d in data])
    pvals = np.array([d['pvalue'] for d in data])
    neg_log_pval = -np.log10(pvals + 1e-300)

    # Color by significance
    colors = []
    for i in range(len(data)):
        if abs(log2fc[i]) >= fc_threshold and pvals[i] <= pval_threshold:
            colors.append('red' if log2fc[i] > 0 else 'blue')
        else:
            colors.append('gray')

    ax.scatter(log2fc, neg_log_pval, c=colors, s=10, alpha=0.6)

    # Threshold lines
    ax.axhline(y=-np.log10(pval_threshold), color='gray', linestyle='--', linewidth=0.5)
    ax.axvline(x=fc_threshold, color='gray', linestyle='--', linewidth=0.5)
    ax.axvline(x=-fc_threshold, color='gray', linestyle='--', linewidth=0.5)

    ax.set_xlabel('Log2 Fold Change')
    ax.set_ylabel('-Log10 P-value')
    ax.set_title(title, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_survival_curve(
    curves: Dict[str, Dict[str, List[float]]],
    output_path: Path,
    title: str = "Kaplan-Meier Survival Curve",
    format: str = "pdf",
) -> bool:
    """
    Generate Kaplan-Meier survival curve.

    Args:
        curves: Dict of {group: {time: [...], survival: [...], ci_lower?: [...], ci_upper?: [...]}}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for survival curve", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(curves)))

    for i, (name, data) in enumerate(curves.items()):
        time = data['time']
        survival = data['survival']
        ax.step(time, survival, where='post', color=colors[i], linewidth=1.5, label=name)

        if 'ci_lower' in data and 'ci_upper' in data:
            ax.fill_between(time, data['ci_lower'], data['ci_upper'],
                          step='post', alpha=0.2, color=colors[i])

    ax.set_xlim([0, None])
    ax.set_ylim([0, 1.05])
    ax.set_xlabel('Time')
    ax.set_ylabel('Survival Probability')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower left', fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_manhattan_plot(
    data: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Manhattan Plot",
    format: str = "pdf",
    genome_wide_line: float = 5e-8,
    suggestive_line: float = 1e-5,
) -> bool:
    """
    Generate Manhattan plot for GWAS results.

    Args:
        data: List of {chr, pos, pvalue} dicts
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        genome_wide_line: P-value threshold for genome-wide significance
        suggestive_line: P-value threshold for suggestive significance

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for Manhattan plot", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Sort by chromosome and position
    sorted_data = sorted(data, key=lambda x: (x['chr'], x['pos']))

    # Calculate cumulative positions
    chr_offset = {}
    current_offset = 0
    prev_chr = None

    x_positions = []
    colors_list = []
    neg_log_pvals = []

    chr_colors = ['#1f77b4', '#aec7e8']

    for d in sorted_data:
        chr_num = d['chr']
        if chr_num != prev_chr:
            if prev_chr is not None:
                current_offset += max(p['pos'] for p in sorted_data if p['chr'] == prev_chr) + 1e7
            chr_offset[chr_num] = current_offset
            prev_chr = chr_num

        x_pos = chr_offset[chr_num] + d['pos']
        x_positions.append(x_pos)
        neg_log_pvals.append(-np.log10(d['pvalue'] + 1e-300))
        colors_list.append(chr_colors[int(chr_num) % 2] if isinstance(chr_num, int) else chr_colors[0])

    ax.scatter(x_positions, neg_log_pvals, c=colors_list, s=5, alpha=0.7)

    # Significance lines
    ax.axhline(y=-np.log10(genome_wide_line), color='red', linestyle='--', linewidth=0.5, label='Genome-wide')
    ax.axhline(y=-np.log10(suggestive_line), color='blue', linestyle='--', linewidth=0.5, label='Suggestive')

    ax.set_xlabel('Chromosome')
    ax.set_ylabel('-Log10 P-value')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='upper right', fontsize=6)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True
