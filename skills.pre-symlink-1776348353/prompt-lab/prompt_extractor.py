"""
Prompt Extractor
Extracts variables ending in _PROMPT from Python files using AST.
"""
import ast
from pathlib import Path
from typing import Dict

class PromptExtractor:
    @staticmethod
    def extract_from_file(filepath: Path) -> Dict[str, str]:
        """
        Extract all string variables ending in _PROMPT from a Python file.
        Returns a dictionary {variable_name: content}.
        """
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
            
        try:
            tree = ast.parse(filepath.read_text())
        except Exception as e:
            raise ValueError(f"Failed to parse {filepath}: {e}")
            
        prompts = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith('_PROMPT'):
                        # Check if value is a string constant
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            prompts[target.id] = node.value.value
                        # Also handle JoinedStr if it's just a simple f-string (might be complex to resolve, skip for now or warn)
                        
        return prompts

    @staticmethod
    def save_prompts(prompts: Dict[str, str], output_dir: Path, prefix: str = ""):
        """Save extracted prompts to text files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for name, content in prompts.items():
            filename = f"{prefix}{name}.txt"
            (output_dir / filename).write_text(content)

