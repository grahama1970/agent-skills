#!/usr/bin/env python3
"""
Machine learning visualization module for fixture-graph skill.

Handles ML/LLM evaluation and training visualizations:
- Confusion matrices
- ROC and PR curves
- Training curves
- Attention heatmaps
- Embedding scatter plots
- Scaling law plots
- Roofline plots
- Throughput vs latency
- Violin plots (biology/ML)
- Volcano plots (biology)
- Survival curves (biology)
- Manhattan plots (genomics)
- Feature importance
- Calibration plots
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from config import IEEE_SINGLE_COLUMN, IEEE_DOUBLE_COLUMN
from utils import check_matplotlib, check_seaborn, apply_ieee_style, get_numpy


def generate_confusion_matrix(
    matrix: List[List[int]],
    labels: List[str],
    output_path: Path,
    title: str = "Confusion Matrix",
    format: str = "pdf",
    normalize: bool = False,
    cmap: str = "Blues",
) -> bool:
    """
    Generate confusion matrix heatmap.

    Args:
        matrix: 2D confusion matrix
        labels: Class labels
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        normalize: Normalize to percentages
        cmap: Colormap name

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for confusion matrix", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    cm = np.array(matrix)
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1, keepdims=True)
        fmt = '.2f'
    else:
        fmt = 'd'

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    if check_seaborn():
        import seaborn as sns
        sns.heatmap(cm, annot=True, fmt=fmt, cmap=cmap, xticklabels=labels,
                   yticklabels=labels, ax=ax, cbar_kws={'shrink': 0.8})
    else:
        im = ax.imshow(cm, cmap=cmap)
        ax.set_xticks(range(len(labels)))
        ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.set_yticklabels(labels)
        plt.colorbar(im, ax=ax, shrink=0.8)

        # Add annotations
        for i in range(len(labels)):
            for j in range(len(labels)):
                text = f'{cm[i, j]:{fmt}}'
                ax.text(j, i, text, ha='center', va='center', fontsize=7)

    ax.set_xlabel('Predicted')
    ax.set_ylabel('True')
    ax.set_title(title, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_roc_curve(
    curves: Dict[str, Dict[str, Any]],
    output_path: Path,
    title: str = "ROC Curve",
    format: str = "pdf",
) -> bool:
    """
    Generate ROC curve for binary classification.

    Args:
        curves: Dict of {name: {fpr: [...], tpr: [...], auc: float}}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for ROC curve", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(curves)))

    for i, (name, data) in enumerate(curves.items()):
        fpr = data.get('fpr', [])
        tpr = data.get('tpr', [])
        auc_val = data.get('auc', 0)
        ax.plot(fpr, tpr, color=colors[i], linewidth=1.5,
               label=f'{name} (AUC={auc_val:.3f})')

    # Diagonal line
    ax.plot([0, 1], [0, 1], 'k--', linewidth=0.5, label='Random')

    ax.set_xlabel('False Positive Rate')
    ax.set_ylabel('True Positive Rate')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower right', fontsize=7)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.05])
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_precision_recall(
    curves: Dict[str, Dict[str, Any]],
    output_path: Path,
    title: str = "Precision-Recall Curve",
    format: str = "pdf",
) -> bool:
    """
    Generate Precision-Recall curve for classification.

    Args:
        curves: Dict of {name: {precision: [...], recall: [...], ap: float}}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for PR curve", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(curves)))

    for i, (name, data) in enumerate(curves.items()):
        precision = data.get('precision', [])
        recall = data.get('recall', [])
        ap = data.get('ap', 0)
        ax.plot(recall, precision, color=colors[i], linewidth=1.5,
               label=f'{name} (AP={ap:.3f})')

    ax.set_xlabel('Recall')
    ax.set_ylabel('Precision')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower left', fontsize=7)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.05])
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_training_curves(
    runs: Dict[str, Dict[str, Any]],
    output_path: Path,
    x_label: str = "Step",
    y_label: str = "Loss",
    title: str = "Training Curves",
    format: str = "pdf",
    log_y: bool = False,
) -> bool:
    """
    Generate training curves for multiple runs.

    Args:
        runs: Dict of {name: {x: [...], y: [...], std?: [...]}}
        output_path: Output file path
        x_label: X-axis label
        y_label: Y-axis label
        title: Chart title
        format: Output format (pdf, png, svg)
        log_y: Use log scale for Y axis

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for training curves", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 3))

    colors = plt.cm.tab10(np.linspace(0, 1, len(runs)))

    for i, (name, data) in enumerate(runs.items()):
        x = data.get('x', list(range(len(data.get('y', [])))))
        y = data.get('y', [])

        ax.plot(x, y, color=colors[i], linewidth=1.5, label=name)

        # Add confidence band if std provided
        if 'std' in data:
            std = np.array(data['std'])
            y_arr = np.array(y)
            ax.fill_between(x, y_arr - std, y_arr + std, color=colors[i], alpha=0.2)

    if log_y:
        ax.set_yscale('log')

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='upper right', fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_attention_heatmap(
    weights: List[List[float]],
    tokens: List[str],
    output_path: Path,
    title: str = "Attention Weights",
    format: str = "pdf",
    cmap: str = "Blues",
) -> bool:
    """
    Generate attention heatmap for transformer models.

    Args:
        weights: 2D attention matrix
        tokens: Token labels for axes
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        cmap: Colormap name

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for attention heatmap", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    weights_arr = np.array(weights)
    n_tokens = len(tokens)

    figsize = max(IEEE_SINGLE_COLUMN, n_tokens * 0.3)
    fig, ax = plt.subplots(figsize=(figsize, figsize))

    if check_seaborn():
        import seaborn as sns
        sns.heatmap(weights_arr, annot=False, cmap=cmap,
                   xticklabels=tokens, yticklabels=tokens, ax=ax)
    else:
        im = ax.imshow(weights_arr, cmap=cmap)
        ax.set_xticks(range(n_tokens))
        ax.set_yticks(range(n_tokens))
        ax.set_xticklabels(tokens, rotation=45, ha='right', fontsize=6)
        ax.set_yticklabels(tokens, fontsize=6)
        plt.colorbar(im, ax=ax, shrink=0.8)

    ax.set_xlabel('Key')
    ax.set_ylabel('Query')
    ax.set_title(title, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_embedding_scatter(
    embeddings: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Embedding Space",
    format: str = "pdf",
    method: str = "tsne",
    perplexity: int = 30,
) -> bool:
    """
    Generate t-SNE or UMAP scatter plot of embeddings.

    Args:
        embeddings: List of {vector: [...], label: str}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        method: Reduction method (tsne, umap)
        perplexity: t-SNE perplexity parameter

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for embedding scatter", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    vectors = np.array([e['vector'] for e in embeddings])
    labels = [e.get('label', '') for e in embeddings]
    unique_labels = list(set(labels))

    # Reduce dimensionality
    try:
        if method == "tsne":
            from sklearn.manifold import TSNE
            reducer = TSNE(n_components=2, perplexity=min(perplexity, len(vectors)-1), random_state=42)
        else:
            from umap import UMAP
            reducer = UMAP(n_components=2, random_state=42)

        reduced = reducer.fit_transform(vectors)
    except ImportError:
        typer.echo(f"[WARN] {method} not available, using PCA", err=True)
        # Fallback to simple PCA
        centered = vectors - vectors.mean(axis=0)
        _, _, Vt = np.linalg.svd(centered)
        reduced = centered @ Vt[:2].T

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(unique_labels)))
    color_map = {label: colors[i] for i, label in enumerate(unique_labels)}

    for label in unique_labels:
        mask = [l == label for l in labels]
        points = reduced[mask]
        ax.scatter(points[:, 0], points[:, 1], c=[color_map[label]],
                  label=label, s=30, alpha=0.7)

    ax.set_xlabel('Dimension 1')
    ax.set_ylabel('Dimension 2')
    ax.set_title(title, fontweight="bold")
    if len(unique_labels) <= 10:
        ax.legend(loc='upper right', fontsize=6)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_scaling_law_plot(
    data: List[Dict[str, float]],
    output_path: Path,
    x_label: str = "Parameters",
    y_label: str = "Loss",
    title: str = "Scaling Law",
    format: str = "pdf",
    fit_power_law: bool = True,
) -> bool:
    """
    Generate scaling law plot (log-log) common in LLM research.

    Args:
        data: List of {x, y} dicts
        output_path: Output file path
        x_label: X-axis label
        y_label: Y-axis label
        title: Chart title
        format: Output format (pdf, png, svg)
        fit_power_law: Fit and show power law line

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for scaling law plot", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    x = np.array([d['x'] for d in data])
    y = np.array([d['y'] for d in data])

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    ax.loglog(x, y, 'o', markersize=8, color='steelblue', markeredgecolor='black')

    if fit_power_law and len(x) >= 2:
        # Fit power law: y = a * x^b  =>  log(y) = log(a) + b*log(x)
        log_x = np.log10(x)
        log_y = np.log10(y)
        coeffs = np.polyfit(log_x, log_y, 1)
        b, log_a = coeffs
        a = 10 ** log_a

        x_fit = np.logspace(np.log10(x.min()), np.log10(x.max()), 100)
        y_fit = a * x_fit ** b

        ax.loglog(x_fit, y_fit, 'r--', linewidth=1.5,
                 label=f'$y = {a:.2e} \\cdot x^{{{b:.2f}}}$')
        ax.legend(fontsize=7)

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title, fontweight="bold")
    ax.grid(True, which='both', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_roofline_plot(
    peak_flops: float,
    peak_bandwidth: float,
    kernels: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Roofline Plot",
    format: str = "pdf",
) -> bool:
    """
    Generate roofline plot for GPU/hardware performance analysis.

    Args:
        peak_flops: Peak FLOPS (e.g., 19.5e12 for V100)
        peak_bandwidth: Peak memory bandwidth in bytes/s (e.g., 900e9)
        kernels: List of {name, flops, bytes, time_s} dicts
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for roofline plot", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Ridge point: where memory-bound meets compute-bound
    ridge_intensity = peak_flops / peak_bandwidth

    # Draw roofline
    intensities = np.logspace(-2, 4, 100)
    roofline = np.minimum(peak_flops, intensities * peak_bandwidth)
    ax.loglog(intensities, roofline, 'b-', linewidth=2, label='Roofline')

    # Mark ridge point
    ax.axvline(x=ridge_intensity, color='gray', linestyle='--', linewidth=0.5)
    ax.text(ridge_intensity, peak_flops * 0.5, f'Ridge\n{ridge_intensity:.1f} FLOP/B',
           fontsize=6, ha='center')

    # Plot kernels
    colors = plt.cm.tab10(np.linspace(0, 1, len(kernels)))
    for i, kernel in enumerate(kernels):
        flops = kernel.get('flops', 0)
        mem_bytes = kernel.get('bytes', 1)
        time_s = kernel.get('time_s', 1)

        intensity = flops / mem_bytes
        achieved_flops = flops / time_s

        ax.scatter(intensity, achieved_flops, color=colors[i], s=80,
                  label=kernel.get('name', f'Kernel {i}'), zorder=5)

    ax.set_xlabel('Arithmetic Intensity (FLOP/Byte)')
    ax.set_ylabel('Performance (FLOP/s)')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower right', fontsize=6)
    ax.grid(True, which='both', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_throughput_latency(
    data: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Throughput vs Latency",
    format: str = "pdf",
) -> bool:
    """
    Generate throughput vs latency plot for GPU/inference benchmarks.

    Args:
        data: List of {name, throughput, latency, batch_size?} dicts
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for throughput-latency plot", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    throughputs = [d['throughput'] for d in data]
    latencies = [d['latency'] for d in data]
    names = [d.get('name', f'Point {i}') for i, d in enumerate(data)]
    batch_sizes = [d.get('batch_size', None) for d in data]

    scatter = ax.scatter(latencies, throughputs, c=range(len(data)),
                        cmap='viridis', s=80, edgecolor='black', zorder=5)

    # Add labels
    for i, (name, lat, thr) in enumerate(zip(names, latencies, throughputs)):
        label = f'{name}'
        if batch_sizes[i]:
            label += f' (B={batch_sizes[i]})'
        ax.annotate(label, (lat, thr), xytext=(5, 5), textcoords='offset points',
                   fontsize=6, bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7))

    ax.set_xlabel('Latency (ms)')
    ax.set_ylabel('Throughput (samples/s)')
    ax.set_title(title, fontweight="bold")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


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


def generate_feature_importance(
    features: Dict[str, float],
    output_path: Path,
    title: str = "Feature Importance",
    format: str = "pdf",
    top_n: int = 20,
) -> bool:
    """
    Generate horizontal bar chart of feature importances.

    Args:
        features: Dict of {feature_name: importance_score}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        top_n: Show top N features

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for feature importance plot", err=True)
        return False

    import matplotlib.pyplot as plt
    apply_ieee_style()

    # Sort by importance and take top N
    sorted_features = sorted(features.items(), key=lambda x: x[1], reverse=True)[:top_n]
    names = [f[0] for f in sorted_features][::-1]
    values = [f[1] for f in sorted_features][::-1]

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN * 1.2))

    ax.barh(range(len(names)), values, color='#1f77b4', alpha=0.8)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=7)
    ax.set_xlabel('Importance')
    ax.set_title(title, fontweight="bold")
    ax.grid(True, alpha=0.3, axis='x')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_calibration_plot(
    data: Dict[str, Dict[str, List[float]]],
    output_path: Path,
    title: str = "Calibration Plot",
    format: str = "pdf",
) -> bool:
    """
    Generate calibration plot (reliability diagram) for classification.

    Args:
        data: Dict of {model_name: {predicted_probs: [...], true_fractions: [...]}}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for calibration plot", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Diagonal line (perfect calibration)
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, label='Perfectly calibrated')

    colors = plt.cm.tab10(np.linspace(0, 1, len(data)))

    for i, (name, d) in enumerate(data.items()):
        predicted = d['predicted_probs']
        actual = d['true_fractions']
        ax.plot(predicted, actual, 's-', color=colors[i], linewidth=1.5,
               markersize=4, label=name)

    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])
    ax.set_xlabel('Mean Predicted Probability')
    ax.set_ylabel('Fraction of Positives')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower right', fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True
