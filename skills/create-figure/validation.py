#!/usr/bin/env python3
"""
Input validation framework for fixture-graph skill.

Provides comprehensive validation for all visualization input types
to ensure reliability and user-friendly error messages.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple


class ValidationError(Exception):
    """Custom exception for validation errors with helpful messages."""
    pass


def validate_json_file(file_path: Path, expected_structure: str = "") -> Dict[str, Any]:
    """
    Validate and load JSON file with comprehensive error handling.
    
    Args:
        file_path: Path to JSON file
        expected_structure: Description of expected structure for error messages
    
    Returns:
        Parsed JSON data
    
    Raises:
        ValidationError: If file doesn't exist or JSON is invalid
    """
    if not file_path.exists():
        raise ValidationError(f"Input file not found: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON in {file_path}: {e}")
    except Exception as e:
        raise ValidationError(f"Error reading {file_path}: {e}")


def validate_scaling_data(data: Any) -> List[Dict[str, float]]:
    """
    Validate scaling law data format.
    
    Expected format: List of dicts with 'x' and 'y' keys
    Accepts: List[Dict], Dict (converted to list), or raw lists
    
    Args:
        data: Input data to validate
    
    Returns:
        Validated list of data points
    
    Raises:
        ValidationError: If data format is invalid
    """
    if isinstance(data, dict):
        # Convert single dict to list format
        if 'x' in data and 'y' in data:
            # Assume it's a single point or needs conversion
            if isinstance(data['x'], list) and isinstance(data['y'], list):
                # Convert parallel arrays to list of dicts
                if len(data['x']) == len(data['y']):
                    return [{'x': float(x), 'y': float(y)} for x, y in zip(data['x'], data['y'])]
                else:
                    raise ValidationError("'x' and 'y' arrays must have the same length")
            else:
                # Single point
                return [{'x': float(data['x']), 'y': float(data['y'])}]
        else:
            raise ValidationError("Scaling data must contain 'x' and 'y' keys")
    
    elif isinstance(data, list):
        if not data:
            raise ValidationError("Scaling data cannot be empty")
        
        validated_data = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                if 'x' not in item or 'y' not in item:
                    raise ValidationError(f"Item {i} must contain 'x' and 'y' keys")
                try:
                    x_val = float(item['x'])
                    y_val = float(item['y'])
                    if x_val <= 0:
                        raise ValidationError(f"Item {i}: 'x' must be positive for log scale")
                    if y_val <= 0:
                        raise ValidationError(f"Item {i}: 'y' must be positive for log scale")
                    validated_data.append({'x': x_val, 'y': y_val})
                except (ValueError, TypeError):
                    raise ValidationError(f"Item {i}: 'x' and 'y' must be numeric")
            else:
                raise ValidationError(f"Item {i} must be a dictionary with 'x' and 'y' keys")
        
        return validated_data
    
    else:
        raise ValidationError("Scaling data must be a list of dictionaries or a dictionary with 'x' and 'y' keys")


def validate_metrics_data(data: Any) -> Dict[str, float]:
    """
    Validate metrics chart data format.
    
    Args:
        data: Input data to validate
    
    Returns:
        Validated dictionary of label -> value pairs
    
    Raises:
        ValidationError: If data format is invalid
    """
    if not isinstance(data, dict):
        raise ValidationError("Metrics data must be a dictionary")
    
    if not data:
        raise ValidationError("Metrics data cannot be empty")
    
    validated_data = {}
    for key, value in data.items():
        try:
            validated_data[str(key)] = float(value)
        except (ValueError, TypeError):
            raise ValidationError(f"Value for key '{key}' must be numeric")
    
    return validated_data


def validate_flow_data(data: Any) -> List[Dict[str, Any]]:
    """
    Validate Sankey diagram flow data.
    
    Args:
        data: Input data to validate
    
    Returns:
        Validated list of flow dictionaries
    
    Raises:
        ValidationError: If data format is invalid
    """
    if not isinstance(data, list):
        raise ValidationError("Flow data must be a list")
    
    if not data:
        raise ValidationError("Flow data cannot be empty")
    
    validated_flows = []
    for i, flow in enumerate(data):
        if not isinstance(flow, dict):
            raise ValidationError(f"Flow {i} must be a dictionary")
        
        required_keys = ['source', 'target', 'value']
        for key in required_keys:
            if key not in flow:
                raise ValidationError(f"Flow {i} must contain '{key}' key")
        
        try:
            validated_flow = {
                'source': str(flow['source']),
                'target': str(flow['target']),
                'value': float(flow['value'])
            }
            
            if validated_flow['value'] < 0:
                raise ValidationError(f"Flow {i}: 'value' must be non-negative")
            
            validated_flows.append(validated_flow)
        except (ValueError, TypeError):
            raise ValidationError(f"Flow {i}: 'value' must be numeric")
    
    return validated_flows


def validate_heatmap_data(data: Any) -> Dict[str, Dict[str, float]]:
    """
    Validate heatmap data format.
    
    Args:
        data: Input data to validate
    
    Returns:
        Validated nested dictionary structure
    
    Raises:
        ValidationError: If data format is invalid
    """
    if not isinstance(data, dict):
        raise ValidationError("Heatmap data must be a dictionary")
    
    if not data:
        raise ValidationError("Heatmap data cannot be empty")
    
    validated_data = {}
    column_keys = None
    
    for row_key, row_data in data.items():
        if not isinstance(row_data, dict):
            raise ValidationError(f"Row '{row_key}' must be a dictionary")
        
        if not row_data:
            raise ValidationError(f"Row '{row_key}' cannot be empty")
        
        # Check column consistency
        if column_keys is None:
            column_keys = set(row_data.keys())
        elif set(row_data.keys()) != column_keys:
            raise ValidationError(f"Row '{row_key}' has inconsistent columns")
        
        validated_row = {}
        for col_key, value in row_data.items():
            try:
                validated_row[str(col_key)] = float(value)
            except (ValueError, TypeError):
                raise ValidationError(f"Row '{row_key}', Column '{col_key}': value must be numeric")
        
        validated_data[str(row_key)] = validated_row
    
    return validated_data


def validate_network_data(nodes: Any, edges: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate network graph data (nodes and edges).
    
    Args:
        nodes: Node data to validate
        edges: Edge data to validate
    
    Returns:
        Validated nodes and edges
    
    Raises:
        ValidationError: If data format is invalid
    """
    if not isinstance(nodes, list):
        raise ValidationError("Nodes must be a list")
    
    if not isinstance(edges, list):
        raise ValidationError("Edges must be a list")
    
    if not nodes:
        raise ValidationError("Nodes list cannot be empty")
    
    # Validate nodes
    validated_nodes = []
    node_ids = set()
    
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValidationError(f"Node {i} must be a dictionary")
        
        if 'id' not in node and 'label' not in node:
            raise ValidationError(f"Node {i} must contain 'id' or 'label' key")
        
        node_id = str(node.get('id', node.get('label', f'node_{i}')))
        if node_id in node_ids:
            raise ValidationError(f"Duplicate node ID: {node_id}")
        
        node_ids.add(node_id)
        
        validated_node = {'id': node_id}
        if 'label' in node:
            validated_node['label'] = str(node['label'])
        if 'group' in node:
            validated_node['group'] = node['group']
        
        validated_nodes.append(validated_node)
    
    # Validate edges
    validated_edges = []
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValidationError(f"Edge {i} must be a dictionary")
        
        if 'source' not in edge or 'target' not in edge:
            raise ValidationError(f"Edge {i} must contain 'source' and 'target' keys")
        
        source = str(edge['source'])
        target = str(edge['target'])
        
        if source not in node_ids:
            raise ValidationError(f"Edge {i}: source node '{source}' not found in nodes")
        if target not in node_ids:
            raise ValidationError(f"Edge {i}: target node '{target}' not found in nodes")
        
        validated_edge = {'source': source, 'target': target}
        
        if 'weight' in edge:
            try:
                validated_edge['weight'] = float(edge['weight'])
            except (ValueError, TypeError):
                raise ValidationError(f"Edge {i}: 'weight' must be numeric")
        
        validated_edges.append(validated_edge)
    
    return validated_nodes, validated_edges


def validate_output_path(output_path: Path, allowed_formats: List[str]) -> str:
    """
    Validate output path and extract format.
    
    Args:
        output_path: Output file path
        allowed_formats: List of allowed file formats
    
    Returns:
        Extracted file format
    
    Raises:
        ValidationError: If format is not supported
    """
    if not output_path.suffix:
        raise ValidationError(f"Output path must have a file extension. Allowed formats: {', '.join(allowed_formats)}")
    
    format_ext = output_path.suffix.lstrip(".").lower()
    
    if format_ext not in allowed_formats:
        raise ValidationError(f"Unsupported format '{format_ext}'. Allowed formats: {', '.join(allowed_formats)}")
    
    return format_ext


def create_validation_error_message(error: ValidationError, context: str = "") -> str:
    """
    Create user-friendly error message with suggestions.
    
    Args:
        error: The validation error
        context: Additional context about what was being validated
    
    Returns:
        Formatted error message with suggestions
    """
    base_message = str(error)
    
    if "scaling" in base_message.lower():
        return f"{base_message}\n\nExpected format for scaling law data:\n" \
               f"- List of dictionaries: [{{'x': 100, 'y': 0.05}}, {{'x': 1000, 'y': 0.01}}]\n" \
               f"- Or parallel arrays: {{'x': [100, 1000], 'y': [0.05, 0.01]}}\n" \
               f"- Values must be positive for log-scale plotting"
    
    elif "metrics" in base_message.lower():
        return f"{base_message}\n\nExpected format for metrics data:\n" \
               f"- Dictionary: {{'Label1': value1, 'Label2': value2}}\n" \
               f"- All values must be numeric"
    
    elif "flow" in base_message.lower():
        return f"{base_message}\n\nExpected format for flow data:\n" \
               f"- List of dictionaries: [{{'source': 'A', 'target': 'B', 'value': 100}}]\n" \
               f"- All values must be non-negative numbers"
    
    elif "heatmap" in base_message.lower():
        return f"{base_message}\n\nExpected format for heatmap data:\n" \
               f"- Nested dictionary: {{'row1': {{'col1': value1, 'col2': value2}}}}\n" \
               f"- All rows must have the same columns"
    
    elif "network" in base_message.lower():
        return f"{base_message}\n\nExpected format for network data:\n" \
               f"- nodes: [{{'id': 'A', 'label': 'Node A'}}, {{'id': 'B'}}]\n" \
               f"- edges: [{{'source': 'A', 'target': 'B', 'weight': 1.0}}]\n" \
               f"- All edge sources/targets must exist in nodes"
    
    else:
        return base_message