#!/usr/bin/env python3
"""
Control systems visualization module for fixture-graph skill.

Handles aerospace, control, and signal processing visualizations:
- Bode plots
- Nyquist plots
- Root locus
- Pole-zero maps
- State-space analysis
- Spectrograms
- Filter response
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer

from config import IEEE_SINGLE_COLUMN, IEEE_DOUBLE_COLUMN
from utils import check_matplotlib, check_control, check_scipy, apply_ieee_style, get_numpy


def generate_bode_plot(
    num: List[float],
    den: List[float],
    output_path: Path,
    title: str = "Bode Plot",
    format: str = "pdf",
    freq_range: Tuple[float, float] = (0.01, 100),
) -> bool:
    """
    Generate Bode plot (magnitude and phase vs frequency).

    Args:
        num: Numerator coefficients (highest power first)
        den: Denominator coefficients (highest power first)
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        freq_range: (min, max) frequency in rad/s

    Returns:
        True if successful, False otherwise
    """
    if check_control():
        return generate_bode_control(num, den, output_path, title, format, freq_range)
    elif check_scipy():
        return generate_bode_scipy(num, den, output_path, title, format, freq_range)
    else:
        typer.echo("[ERROR] python-control or scipy required for Bode plot", err=True)
        return False


def generate_bode_control(
    num: List[float],
    den: List[float],
    output_path: Path,
    title: str,
    format: str,
    freq_range: Tuple[float, float],
) -> bool:
    """Generate Bode plot using python-control."""
    import control
    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    sys = control.TransferFunction(num, den)
    omega = np.logspace(np.log10(freq_range[0]), np.log10(freq_range[1]), 500)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN * 1.5))

    mag, phase, omega = control.bode(sys, omega, plot=False)

    ax1.semilogx(omega, 20 * np.log10(mag), 'b-', linewidth=1.5)
    ax1.set_ylabel('Magnitude (dB)')
    ax1.set_title(title, fontweight="bold")
    ax1.grid(True, which='both', alpha=0.3)
    ax1.axhline(y=0, color='k', linestyle='--', linewidth=0.5)

    ax2.semilogx(omega, np.degrees(phase), 'b-', linewidth=1.5)
    ax2.set_xlabel('Frequency (rad/s)')
    ax2.set_ylabel('Phase (deg)')
    ax2.grid(True, which='both', alpha=0.3)
    ax2.axhline(y=-180, color='r', linestyle='--', linewidth=0.5)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_bode_scipy(
    num: List[float],
    den: List[float],
    output_path: Path,
    title: str,
    format: str,
    freq_range: Tuple[float, float],
) -> bool:
    """Generate Bode plot using scipy."""
    from scipy import signal
    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    sys = signal.TransferFunction(num, den)
    w = np.logspace(np.log10(freq_range[0]), np.log10(freq_range[1]), 500)
    w_out, H = signal.freqresp(sys, w)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN * 1.5))

    ax1.semilogx(w_out, 20 * np.log10(np.abs(H)), 'b-', linewidth=1.5)
    ax1.set_ylabel('Magnitude (dB)')
    ax1.set_title(title, fontweight="bold")
    ax1.grid(True, which='both', alpha=0.3)
    ax1.axhline(y=0, color='k', linestyle='--', linewidth=0.5)

    ax2.semilogx(w_out, np.degrees(np.unwrap(np.angle(H))), 'b-', linewidth=1.5)
    ax2.set_xlabel('Frequency (rad/s)')
    ax2.set_ylabel('Phase (deg)')
    ax2.grid(True, which='both', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_nyquist_plot(
    num: List[float],
    den: List[float],
    output_path: Path,
    title: str = "Nyquist Plot",
    format: str = "pdf",
) -> bool:
    """
    Generate Nyquist plot for stability analysis.

    Args:
        num: Numerator coefficients
        den: Denominator coefficients
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not (check_control() or check_scipy()):
        typer.echo("[ERROR] python-control or scipy required for Nyquist plot", err=True)
        return False

    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for Nyquist plot", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    if check_control():
        import control
        sys = control.TransferFunction(num, den)
        omega = np.logspace(-2, 2, 1000)
        _, H = control.frequency_response(sys, omega)
        H = H.flatten()
    else:
        from scipy import signal
        sys = signal.TransferFunction(num, den)
        omega = np.logspace(-2, 2, 1000)
        _, H = signal.freqresp(sys, omega)

    ax.plot(H.real, H.imag, 'b-', linewidth=1.5, label='Positive freq')
    ax.plot(H.real, -H.imag, 'b--', linewidth=1, alpha=0.5, label='Negative freq')
    ax.plot(-1, 0, 'rx', markersize=10, markeredgewidth=2, label='Critical point')

    # Draw unit circle for reference
    theta = np.linspace(0, 2*np.pi, 100)
    ax.plot(np.cos(theta)-1, np.sin(theta), 'k--', alpha=0.3, linewidth=0.5)

    ax.set_xlabel('Real')
    ax.set_ylabel('Imaginary')
    ax.set_title(title, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')
    ax.legend(fontsize=7, loc='upper right')
    ax.axhline(y=0, color='k', linewidth=0.5)
    ax.axvline(x=0, color='k', linewidth=0.5)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_root_locus(
    num: List[float],
    den: List[float],
    output_path: Path,
    title: str = "Root Locus",
    format: str = "pdf",
    show_breakaway: bool = True,
    gain_range: Tuple[float, float] = (0.01, 100),
) -> bool:
    """
    Generate root locus plot for control system gain analysis.

    Args:
        num: Numerator coefficients
        den: Denominator coefficients
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        show_breakaway: Show breakaway points
        gain_range: (min, max) gain for analysis

    Returns:
        True if successful, False otherwise
    """
    if not check_control():
        typer.echo("[ERROR] python-control required for root locus", err=True)
        return False

    import control
    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    sys = control.TransferFunction(num, den)

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    rlist, klist = control.root_locus(sys, kvect=np.logspace(
        np.log10(gain_range[0]), np.log10(gain_range[1]), 500
    ), plot=False)

    # Plot root locus branches
    for i in range(rlist.shape[1]):
        ax.plot(rlist[:, i].real, rlist[:, i].imag, 'b-', linewidth=1)

    # Mark poles and zeros
    poles = control.poles(sys)
    zeros = control.zeros(sys)

    ax.plot(poles.real, poles.imag, 'rx', markersize=10, markeredgewidth=2, label='Poles')
    if len(zeros) > 0:
        ax.plot(zeros.real, zeros.imag, 'go', markersize=8, markerfacecolor='none',
               markeredgewidth=2, label='Zeros')

    ax.axhline(y=0, color='k', linewidth=0.5)
    ax.axvline(x=0, color='k', linewidth=0.5)
    ax.set_xlabel('Real')
    ax.set_ylabel('Imaginary')
    ax.set_title(title, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_pole_zero_map(
    zeros: List[complex],
    poles: List[complex],
    output_path: Path,
    title: str = "Pole-Zero Map",
    format: str = "pdf",
    show_stability_region: bool = True,
    show_damping_lines: bool = True,
    is_discrete: bool = False,
    sample_time: Optional[float] = None,
) -> bool:
    """
    Generate pole-zero map with stability analysis.

    Args:
        zeros: List of zero locations (complex)
        poles: List of pole locations (complex)
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        show_stability_region: Show LHP/unit circle shading
        show_damping_lines: Show damping ratio lines
        is_discrete: Discrete-time system (use unit circle)
        sample_time: Sample time for discrete systems

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for pole-zero map", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Stability region
    if is_discrete:
        # Unit circle for discrete systems
        theta = np.linspace(0, 2*np.pi, 100)
        ax.plot(np.cos(theta), np.sin(theta), 'k--', linewidth=1, alpha=0.5)
        if show_stability_region:
            ax.fill(np.cos(theta), np.sin(theta), alpha=0.1, color='green')
    else:
        # Left half plane for continuous systems
        if show_stability_region:
            ax.axvspan(-10, 0, alpha=0.1, color='green')
        ax.axvline(x=0, color='k', linestyle='--', linewidth=0.5)

    # Damping ratio lines (continuous only)
    if show_damping_lines and not is_discrete:
        for zeta in [0.1, 0.3, 0.5, 0.7, 0.9]:
            theta = np.arccos(zeta)
            r = np.linspace(0, 5, 100)
            ax.plot(-r * np.cos(theta), r * np.sin(theta), 'k:', alpha=0.3, linewidth=0.5)
            ax.plot(-r * np.cos(theta), -r * np.sin(theta), 'k:', alpha=0.3, linewidth=0.5)

    # Plot poles
    for p in poles:
        ax.plot(p.real, p.imag, 'rx', markersize=12, markeredgewidth=2)

    # Plot zeros
    for z in zeros:
        ax.plot(z.real, z.imag, 'go', markersize=10, markerfacecolor='none', markeredgewidth=2)

    ax.axhline(y=0, color='k', linewidth=0.5)
    ax.set_xlabel('Real')
    ax.set_ylabel('Imaginary')
    ax.set_title(title, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')

    # Add legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='x', color='r', linestyle='None', markersize=10, label='Poles'),
        Line2D([0], [0], marker='o', color='g', linestyle='None', markersize=8,
               markerfacecolor='none', label='Zeros'),
    ]
    ax.legend(handles=legend_elements, fontsize=7)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_state_space_visualization(
    A: List[List[float]],
    B: List[List[float]],
    C: List[List[float]],
    D: List[List[float]],
    output_path: Path,
    title: str = "State Space System",
    format: str = "pdf",
    show_poles_zeros: bool = True,
    show_eigenvalues: bool = True,
) -> bool:
    """
    Generate comprehensive state-space system visualization.

    Args:
        A, B, C, D: State-space matrices
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        show_poles_zeros: Include pole-zero plot
        show_eigenvalues: Show eigenvalue analysis

    Returns:
        True if successful, False otherwise
    """
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for state-space visualization", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    apply_ieee_style()

    A = np.array(A)
    B = np.array(B)
    C = np.array(C)
    D = np.array(D)

    # Calculate eigenvalues
    eigenvalues = np.linalg.eigvals(A)

    n_plots = 1 + int(show_poles_zeros) + int(show_eigenvalues)
    fig, axes = plt.subplots(1, n_plots, figsize=(IEEE_DOUBLE_COLUMN, 3))
    if n_plots == 1:
        axes = [axes]

    # Plot 1: Matrix visualization
    ax = axes[0]
    ax.matshow(A, cmap='coolwarm')
    ax.set_title('State Matrix A', fontsize=9)
    ax.set_xlabel('Column')
    ax.set_ylabel('Row')

    plot_idx = 1

    # Plot 2: Pole-zero map (if enabled)
    if show_poles_zeros and plot_idx < len(axes):
        ax = axes[plot_idx]
        plot_idx += 1

        ax.plot(eigenvalues.real, eigenvalues.imag, 'rx', markersize=10, markeredgewidth=2)
        ax.axhline(y=0, color='k', linewidth=0.5)
        ax.axvline(x=0, color='k', linewidth=0.5)
        ax.axvspan(-10, 0, alpha=0.1, color='green')
        ax.set_xlabel('Real')
        ax.set_ylabel('Imaginary')
        ax.set_title('Eigenvalues', fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal')

    # Plot 3: Eigenvalue analysis (if enabled)
    if show_eigenvalues and plot_idx < len(axes):
        ax = axes[plot_idx]

        # Bar chart of eigenvalue magnitudes
        magnitudes = np.abs(eigenvalues)
        ax.bar(range(len(magnitudes)), magnitudes, color='steelblue', edgecolor='black')
        ax.set_xlabel('Eigenvalue Index')
        ax.set_ylabel('Magnitude')
        ax.set_title('Eigenvalue Magnitudes', fontsize=9)
        ax.grid(True, axis='y', alpha=0.3)

    fig.suptitle(title, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_spectrogram(
    signal: List[float],
    sample_rate: float,
    output_path: Path,
    title: str = "Spectrogram",
    format: str = "pdf",
    window: str = "hann",
    window_size: int = 256,
    overlap: float = 0.5,
) -> bool:
    """
    Generate spectrogram for time-frequency signal analysis.

    Args:
        signal: Time-domain signal samples
        sample_rate: Sample rate in Hz
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        window: Window type (hann, hamming, blackman, rectangular)
        window_size: FFT window size in samples
        overlap: Overlap fraction (0-1)

    Returns:
        True if successful, False otherwise
    """
    if not check_scipy():
        typer.echo("[ERROR] scipy required for spectrogram", err=True)
        return False

    import matplotlib.pyplot as plt
    from scipy import signal as sig
    import numpy as np
    apply_ieee_style()

    # Get window function
    window_funcs = {
        'hann': 'hann',
        'hamming': 'hamming',
        'blackman': 'blackman',
        'rectangular': 'boxcar',
    }
    window_type = window_funcs.get(window, 'hann')

    overlap_samples = int(window_size * overlap)

    f, t, Sxx = sig.spectrogram(
        np.array(signal),
        fs=sample_rate,
        window=window_type,
        nperseg=window_size,
        noverlap=overlap_samples,
    )

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 3))

    im = ax.pcolormesh(t, f, 10 * np.log10(Sxx + 1e-10), shading='gouraud', cmap='viridis')
    ax.set_ylabel('Frequency [Hz]')
    ax.set_xlabel('Time [sec]')
    ax.set_title(title, fontweight="bold")
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Power/Frequency [dB/Hz]')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_filter_response(
    filter_coeffs: Dict[str, List[float]],
    sample_rate: float,
    output_path: Path,
    title: str = "Filter Response",
    format: str = "pdf",
    freq_range: Optional[Tuple[float, float]] = None,
) -> bool:
    """
    Generate frequency response analysis for digital filters.

    Args:
        filter_coeffs: Dict with 'b' and 'a' coefficient lists
        sample_rate: Sample rate in Hz
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        freq_range: Optional (min, max) frequency in Hz

    Returns:
        True if successful, False otherwise
    """
    if not check_scipy():
        typer.echo("[ERROR] scipy required for filter response", err=True)
        return False

    import matplotlib.pyplot as plt
    from scipy import signal
    import numpy as np
    apply_ieee_style()

    b = np.array(filter_coeffs['b'])
    a = np.array(filter_coeffs['a'])

    w, h = signal.freqz(b, a, worN=2048, fs=sample_rate)

    if freq_range:
        mask = (w >= freq_range[0]) & (w <= freq_range[1])
        w = w[mask]
        h = h[mask]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN * 1.5))

    # Magnitude response
    ax1.plot(w, 20 * np.log10(np.abs(h) + 1e-10), 'b-', linewidth=1.5)
    ax1.set_ylabel('Magnitude [dB]')
    ax1.set_title(title, fontweight="bold")
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=-3, color='r', linestyle='--', linewidth=0.5, label='-3 dB')
    ax1.legend(fontsize=7)

    # Phase response
    ax2.plot(w, np.degrees(np.unwrap(np.angle(h))), 'b-', linewidth=1.5)
    ax2.set_xlabel('Frequency [Hz]')
    ax2.set_ylabel('Phase [deg]')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True
