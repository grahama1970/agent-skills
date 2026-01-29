#!/usr/bin/env python3
"""
Test suite for 3D plotting functions in fixture-graph skill.
Tests 3D surface, 3D contour, and complex plane visualizations.
"""

import json
import tempfile
from pathlib import Path
import pytest
import sys
import os

# Add the parent directory to the path so we can import fixture_graph
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fixture_graph import (
        generate_3d_surface,
        generate_3d_contour,
        generate_complex_plane,
    )
    MATPLOTLIB_AVAILABLE = True
except ImportError as e:
    MATPLOTLIB_AVAILABLE = False
    print(f"matplotlib not available: {e}")

# Check if Axes3D is available (separate from matplotlib due to version conflicts)
AXES3D_AVAILABLE = False
if MATPLOTLIB_AVAILABLE:
    try:
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
        AXES3D_AVAILABLE = True
    except (ImportError, ModuleNotFoundError) as e:
        print(f"Axes3D not available (matplotlib version conflict): {e}")


class Test3DSurfacePlot:
    """Test 3D surface plotting functionality."""

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_basic_surface_plot(self):
        """Test basic 3D surface plot generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "surface_test.pdf"
            
            success = generate_3d_surface(
                x_range=(-2, 2),
                y_range=(-2, 2),
                z_function="sin(x) * cos(y)",
                output_path=output_path,
                title="Test Surface",
                format="pdf",
                resolution=20,  # Lower resolution for faster testing
            )
            
            assert success is True
            assert output_path.exists()
            assert output_path.stat().st_size > 0

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_complex_surface_function(self):
        """Test 3D surface with more complex mathematical function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "complex_surface_test.pdf"
            
            success = generate_3d_surface(
                x_range=(-3, 3),
                y_range=(-3, 3),
                z_function="exp(-(x**2 + y**2)) * sin(sqrt(x**2 + y**2))",
                output_path=output_path,
                title="Gaussian Sine Surface",
                format="pdf",
                resolution=15,
            )
            
            assert success is True
            assert output_path.exists()

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_invalid_function(self):
        """Test error handling for invalid function expressions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "invalid_surface_test.pdf"
            
            success = generate_3d_surface(
                x_range=(-1, 1),
                y_range=(-1, 1),
                z_function="invalid_function(x, y)",  # This should fail
                output_path=output_path,
                title="Invalid Function Test",
            )
            
            assert success is False

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_different_colormaps(self):
        """Test 3D surface with different colormaps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for cmap in ["viridis", "plasma", "coolwarm"]:
                output_path = Path(tmpdir) / f"surface_{cmap}.pdf"
                
                success = generate_3d_surface(
                    x_range=(-2, 2),
                    y_range=(-2, 2),
                    z_function="x**2 + y**2",
                    output_path=output_path,
                    title=f"Paraboloid - {cmap}",
                    colormap=cmap,
                    resolution=15,
                )
                
                assert success is True
                assert output_path.exists()

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_different_view_angles(self):
        """Test 3D surface with different viewing angles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            view_angles = [(0, 0), (30, 45), (60, 90), (90, 0)]
            
            for i, (elev, azim) in enumerate(view_angles):
                output_path = Path(tmpdir) / f"surface_view_{i}.pdf"
                
                success = generate_3d_surface(
                    x_range=(-2, 2),
                    y_range=(-2, 2),
                    z_function="sin(x) + cos(y)",
                    output_path=output_path,
                    title=f"View Angle {elev}°, {azim}°",
                    view_angle=(elev, azim),
                    resolution=15,
                )
                
                assert success is True
                assert output_path.exists()


class Test3DContourPlot:
    """Test 3D contour plotting functionality."""

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_basic_contour_plot(self):
        """Test basic 3D contour plot generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "contour_3d_test.pdf"
            
            success = generate_3d_contour(
                x_range=(-2, 2),
                y_range=(-2, 2),
                z_function="x**2 - y**2",
                output_path=output_path,
                title="Hyperbolic Paraboloid",
                format="pdf",
                resolution=20,
                levels=15,
            )
            
            assert success is True
            assert output_path.exists()
            assert output_path.stat().st_size > 0

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_different_levels(self):
        """Test 3D contour with different number of levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for levels in [5, 15, 30]:
                output_path = Path(tmpdir) / f"contour_levels_{levels}.pdf"
                
                success = generate_3d_contour(
                    x_range=(-2, 2),
                    y_range=(-2, 2),
                    z_function="sin(x) * sin(y)",
                    output_path=output_path,
                    title=f"Contour Levels: {levels}",
                    levels=levels,
                    resolution=15,
                )
                
                assert success is True
                assert output_path.exists()


class TestComplexPlanePlot:
    """Test complex plane visualization functionality."""

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not available")
    def test_basic_complex_plot(self):
        """Test basic complex plane plot generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "complex_plane_test.pdf"
            
            complex_numbers = [1+2j, 3-1j, -2+3j, 0.5-0.5j, 2+0j]
            
            success = generate_complex_plane(
                complex_numbers=complex_numbers,
                output_path=output_path,
                title="Test Complex Numbers",
                format="pdf",
                show_unit_circle=True,
                color_by_magnitude=True,
            )
            
            assert success is True
            assert output_path.exists()
            assert output_path.stat().st_size > 0

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not available")
    def test_empty_complex_list(self):
        """Test error handling for empty complex number list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "empty_complex_test.pdf"
            
            success = generate_complex_plane(
                complex_numbers=[],
                output_path=output_path,
                title="Empty Complex Test",
            )
            
            assert success is False

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not available")
    def test_without_unit_circle(self):
        """Test complex plane without unit circle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "complex_no_circle_test.pdf"
            
            complex_numbers = [1+1j, 2-1j, -1+2j]
            
            success = generate_complex_plane(
                complex_numbers=complex_numbers,
                output_path=output_path,
                title="Complex Plane - No Unit Circle",
                show_unit_circle=False,
                color_by_magnitude=True,
            )
            
            assert success is True
            assert output_path.exists()

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not available")
    def test_without_color_by_magnitude(self):
        """Test complex plane without magnitude coloring."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "complex_no_color_test.pdf"
            
            complex_numbers = [1+2j, 3-1j, -2+3j]
            
            success = generate_complex_plane(
                complex_numbers=complex_numbers,
                output_path=output_path,
                title="Complex Plane - No Color Coding",
                show_unit_circle=True,
                color_by_magnitude=False,
            )
            
            assert success is True
            assert output_path.exists()

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not available")
    def test_large_complex_set(self):
        """Test complex plane with larger set of complex numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "complex_large_test.pdf"
            
            # Generate a set of complex numbers on unit circle and inside
            import math
            complex_numbers = []
            for i in range(20):
                angle = 2 * math.pi * i / 20
                magnitude = 0.5 + 0.5 * math.sin(angle * 3)  # Varying magnitude
                complex_numbers.append(complex(magnitude * math.cos(angle), magnitude * math.sin(angle)))
            
            success = generate_complex_plane(
                complex_numbers=complex_numbers,
                output_path=output_path,
                title="Complex Numbers on Unit Circle",
                show_unit_circle=True,
                color_by_magnitude=True,
            )
            
            assert success is True
            assert output_path.exists()


class TestIntegration:
    """Integration tests for 3D plotting functions."""

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_multiple_formats(self):
        """Test that 3D plots can be generated in different formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            formats = ["pdf", "png", "svg"]
            
            for fmt in formats:
                # Test 3D surface
                surface_path = Path(tmpdir) / f"surface.{fmt}"
                success = generate_3d_surface(
                    x_range=(-1, 1),
                    y_range=(-1, 1),
                    z_function="x + y",
                    output_path=surface_path,
                    format=fmt,
                    resolution=10,
                )
                assert success is True
                assert surface_path.exists()
                
                # Test complex plane
                complex_path = Path(tmpdir) / f"complex.{fmt}"
                success = generate_complex_plane(
                    complex_numbers=[1+1j, 2-1j],
                    output_path=complex_path,
                    format=fmt,
                )
                assert success is True
                assert complex_path.exists()

    @pytest.mark.skipif(not AXES3D_AVAILABLE, reason="Axes3D not available (matplotlib version conflict)")
    def test_mathematical_functions(self):
        """Test various mathematical functions for 3D plotting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions = [
                "x**2 + y**2",  # Paraboloid
                "sin(x) * cos(y)",  # Trigonometric
                "exp(-(x**2 + y**2))",  # Gaussian
                "sqrt(x**2 + y**2)",  # Distance function
                "x**3 - 3*x*y**2",  # Complex polynomial
            ]
            
            for i, func in enumerate(functions):
                # Test surface
                surface_path = Path(tmpdir) / f"surface_func_{i}.pdf"
                success = generate_3d_surface(
                    x_range=(-2, 2),
                    y_range=(-2, 2),
                    z_function=func,
                    output_path=surface_path,
                    title=f"Function: {func}",
                    resolution=15,
                )
                assert success is True
                
                # Test contour
                contour_path = Path(tmpdir) / f"contour_func_{i}.pdf"
                success = generate_3d_contour(
                    x_range=(-2, 2),
                    y_range=(-2, 2),
                    z_function=func,
                    output_path=contour_path,
                    title=f"Contour: {func}",
                    resolution=15,
                )
                assert success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])