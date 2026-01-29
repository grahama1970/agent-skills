#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Tests for the validation framework in fixture-graph skill.

Run with: pytest test_validation.py -v
"""
import json
import tempfile
from pathlib import Path

import pytest

from validation import (
    ValidationError,
    validate_json_file,
    validate_scaling_data,
    validate_metrics_data,
    validate_flow_data,
    validate_heatmap_data,
    validate_network_data,
    validate_output_path,
    create_validation_error_message
)


class TestValidateJsonFile:
    """Tests for JSON file validation."""

    def test_valid_json_file(self):
        """Test validation of valid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"test": "data"}, f)
            f.flush()
            temp_path = Path(f.name)
        
        try:
            result = validate_json_file(temp_path)
            assert result == {"test": "data"}
        finally:
            temp_path.unlink()

    def test_nonexistent_file(self):
        """Test validation of non-existent file."""
        with pytest.raises(ValidationError, match="Input file not found"):
            validate_json_file(Path("nonexistent.json"))

    def test_invalid_json(self):
        """Test validation of invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            f.flush()
            temp_path = Path(f.name)
        
        try:
            with pytest.raises(ValidationError, match="Invalid JSON"):
                validate_json_file(temp_path)
        finally:
            temp_path.unlink()


class TestValidateScalingData:
    """Tests for scaling law data validation."""

    def test_valid_list_format(self):
        """Test valid list of dictionaries format."""
        data = [{"x": 100, "y": 0.05}, {"x": 1000, "y": 0.01}]
        result = validate_scaling_data(data)
        assert result == data

    def test_valid_parallel_arrays(self):
        """Test valid parallel arrays format."""
        data = {"x": [100, 1000], "y": [0.05, 0.01]}
        result = validate_scaling_data(data)
        expected = [{"x": 100.0, "y": 0.05}, {"x": 1000.0, "y": 0.01}]
        assert result == expected

    def test_valid_single_point(self):
        """Test valid single point format."""
        data = {"x": 100, "y": 0.05}
        result = validate_scaling_data(data)
        expected = [{"x": 100.0, "y": 0.05}]
        assert result == expected

    def test_invalid_missing_keys(self):
        """Test data missing required keys."""
        data = {"invalid": "data"}
        with pytest.raises(ValidationError, match="must contain 'x' and 'y' keys"):
            validate_scaling_data(data)

    def test_invalid_mismatched_arrays(self):
        """Test parallel arrays with different lengths."""
        data = {"x": [100, 1000], "y": [0.05]}
        with pytest.raises(ValidationError, match="must have the same length"):
            validate_scaling_data(data)

    def test_invalid_negative_values(self):
        """Test data with negative values."""
        data = [{"x": -100, "y": 0.05}]
        with pytest.raises(ValidationError, match="must be positive"):
            validate_scaling_data(data)

    def test_invalid_non_numeric(self):
        """Test data with non-numeric values."""
        data = [{"x": "invalid", "y": 0.05}]
        with pytest.raises(ValidationError, match="must be numeric"):
            validate_scaling_data(data)

    def test_empty_list(self):
        """Test empty list."""
        data = []
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_scaling_data(data)


class TestValidateMetricsData:
    """Tests for metrics data validation."""

    def test_valid_dict(self):
        """Test valid dictionary format."""
        data = {"A": 100, "B": 200, "C": 150}
        result = validate_metrics_data(data)
        assert result == data

    def test_invalid_type(self):
        """Test non-dictionary input."""
        data = ["invalid"]
        with pytest.raises(ValidationError, match="must be a dictionary"):
            validate_metrics_data(data)

    def test_empty_dict(self):
        """Test empty dictionary."""
        data = {}
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_metrics_data(data)

    def test_non_numeric_values(self):
        """Test dictionary with non-numeric values."""
        data = {"A": "invalid", "B": 200}
        with pytest.raises(ValidationError, match="must be numeric"):
            validate_metrics_data(data)


class TestValidateFlowData:
    """Tests for flow data validation."""

    def test_valid_flows(self):
        """Test valid flow data."""
        data = [{"source": "A", "target": "B", "value": 100}]
        result = validate_flow_data(data)
        assert result == data

    def test_invalid_not_list(self):
        """Test non-list input."""
        data = {"invalid": "data"}
        with pytest.raises(ValidationError, match="must be a list"):
            validate_flow_data(data)

    def test_empty_list(self):
        """Test empty list."""
        data = []
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_flow_data(data)

    def test_missing_required_keys(self):
        """Test flows missing required keys."""
        data = [{"source": "A", "target": "B"}]  # Missing 'value'
        with pytest.raises(ValidationError, match="must contain 'value' key"):
            validate_flow_data(data)

    def test_negative_values(self):
        """Test flows with negative values."""
        data = [{"source": "A", "target": "B", "value": -100}]
        with pytest.raises(ValidationError, match="must be non-negative"):
            validate_flow_data(data)

    def test_non_numeric_values(self):
        """Test flows with non-numeric values."""
        data = [{"source": "A", "target": "B", "value": "invalid"}]
        with pytest.raises(ValidationError, match="must be numeric"):
            validate_flow_data(data)


class TestValidateHeatmapData:
    """Tests for heatmap data validation."""

    def test_valid_heatmap(self):
        """Test valid heatmap data."""
        data = {
            "row1": {"col1": 1.0, "col2": 2.0},
            "row2": {"col1": 3.0, "col2": 4.0}
        }
        result = validate_heatmap_data(data)
        assert result == data

    def test_invalid_not_dict(self):
        """Test non-dictionary input."""
        data = ["invalid"]
        with pytest.raises(ValidationError, match="must be a dictionary"):
            validate_heatmap_data(data)

    def test_empty_dict(self):
        """Test empty dictionary."""
        data = {}
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_heatmap_data(data)

    def test_inconsistent_columns(self):
        """Test rows with different columns."""
        data = {
            "row1": {"col1": 1.0, "col2": 2.0},
            "row2": {"col1": 3.0, "col3": 4.0}  # Different column
        }
        with pytest.raises(ValidationError, match="inconsistent columns"):
            validate_heatmap_data(data)

    def test_non_numeric_values(self):
        """Test non-numeric values."""
        data = {"row1": {"col1": "invalid"}}
        with pytest.raises(ValidationError, match="must be numeric"):
            validate_heatmap_data(data)


class TestValidateNetworkData:
    """Tests for network data validation."""

    def test_valid_network(self):
        """Test valid network data."""
        nodes = [{"id": "A"}, {"id": "B"}]
        edges = [{"source": "A", "target": "B"}]
        result_nodes, result_edges = validate_network_data(nodes, edges)
        assert result_nodes == nodes
        assert result_edges == edges

    def test_nodes_without_id(self):
        """Test nodes without explicit ID."""
        nodes = [{"label": "Node A"}, {"label": "Node B"}]
        edges = [{"source": "Node A", "target": "Node B"}]
        result_nodes, result_edges = validate_network_data(nodes, edges)
        assert len(result_nodes) == 2
        assert result_nodes[0]["id"] == "Node A"
        assert result_nodes[0]["label"] == "Node A"

    def test_invalid_nodes_not_list(self):
        """Test non-list nodes input."""
        nodes = {"invalid": "data"}
        edges = []
        with pytest.raises(ValidationError, match="must be a list"):
            validate_network_data(nodes, edges)

    def test_empty_nodes(self):
        """Test empty nodes list."""
        nodes = []
        edges = []
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_network_data(nodes, edges)

    def test_invalid_edges_not_list(self):
        """Test non-list edges input."""
        nodes = [{"id": "A"}]
        edges = {"invalid": "data"}
        with pytest.raises(ValidationError, match="must be a list"):
            validate_network_data(nodes, edges)

    def test_missing_source_target(self):
            """Test edges missing source or target."""
            nodes = [{"id": "A"}, {"id": "B"}]
            edges = [{"source": "A"}]  # Missing target
            with pytest.raises(ValidationError, match="must contain 'source' and 'target' keys"):
                validate_network_data(nodes, edges)

    def test_nonexistent_node_references(self):
        """Test edges referencing non-existent nodes."""
        nodes = [{"id": "A"}]
        edges = [{"source": "A", "target": "B"}]  # B doesn't exist
        with pytest.raises(ValidationError, match="target node 'B' not found"):
            validate_network_data(nodes, edges)


class TestValidateOutputPath:
    """Tests for output path validation."""

    def test_valid_formats(self):
        """Test valid output formats."""
        allowed_formats = ["pdf", "png", "svg"]
        
        for fmt in allowed_formats:
            path = Path(f"test.{fmt}")
            result = validate_output_path(path, allowed_formats)
            assert result == fmt

    def test_no_extension(self):
        """Test path without extension."""
        path = Path("test")
        allowed_formats = ["pdf", "png"]
        with pytest.raises(ValidationError, match="must have a file extension"):
            validate_output_path(path, allowed_formats)

    def test_unsupported_format(self):
        """Test unsupported file format."""
        path = Path("test.jpg")
        allowed_formats = ["pdf", "png"]
        with pytest.raises(ValidationError, match="Unsupported format"):
            validate_output_path(path, allowed_formats)


class TestCreateValidationErrorMessage:
    """Tests for error message creation."""

    def test_scaling_error_message(self):
        """Test scaling data error message."""
        error = ValidationError("Scaling data must contain 'x' and 'y' keys")
        message = create_validation_error_message(error)
        assert "Expected format for scaling law data" in message
        assert "List of dictionaries" in message

    def test_metrics_error_message(self):
        """Test metrics data error message."""
        error = ValidationError("Metrics data must be a dictionary")
        message = create_validation_error_message(error)
        assert "Expected format for metrics data" in message
        assert "Dictionary" in message

    def test_flow_error_message(self):
        """Test flow data error message."""
        error = ValidationError("Flow data must be a list")
        message = create_validation_error_message(error)
        assert "Expected format for flow data" in message
        assert "List of dictionaries" in message

    def test_generic_error_message(self):
        """Test generic error message."""
        error = ValidationError("Some generic error")
        message = create_validation_error_message(error)
        assert message == "Some generic error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])