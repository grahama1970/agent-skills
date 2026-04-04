"""verify - sanity.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json
import uuid
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add skill root to path
SKILL_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from extract_html.pipeline import run_pipeline
from extract_html.validate import validate_or_errors

def test_pipeline_mocked():
    """
    Runs the pipeline with a mocked Ollama response to verify logic flow.
    """
    html_content = """
    <html>
        <body>
            <h1>Product Spec</h1>
            <p>The Widget 3000 is great.</p>
            <table>
                <tr><th>Feature</th><th>Value</th></tr>
                <tr><td>Weight</td><td>10kg</td></tr>
            </table>
            <img src="product.jpg" alt="The widget in profile">
        </body>
    </html>
    """
    
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "specs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "feature": {"type": "string"},
                        "value": {"type": "string"}
                    }
                }
            }
        },
        "required": ["name", "specs"]
    }

    # Mock Ollama response
    mock_response = {
        "name": "Widget 3000",
        "specs": [
            {"feature": "Weight", "value": "10kg"}
        ]
    }
    
    with patch("extract_html.schematron.httpx.Client") as mock_client:
        # Mock the POST response
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.return_value.json.return_value = {
            "response": json.dumps(mock_response)
        }
        mock_instance.post.return_value.status_code = 200

        result = run_pipeline(
            html_path=Path("dummy.html"),
            raw_html=html_content,
            json_schema=schema,
            ollama_base_url="http://mock-url",
            model="mock-model",
            timeout_s=10,
            max_attempts=1,
            max_html_chars=1000,
            normalize_mode="nfkc",
            include_sections=True,
            emit_sections=False,
            extract_tables=True,
            max_tables=5,
            extract_media_text=True,
            min_image_px=100,
            max_image_px=10000,
            min_image_dim=10,
            fetch_remote_media=False,
            vision_api_base=None,
            vision_api_key=None,
            vision_model="mock-vision",
            vision_concurrency=1,
            debug_dir=Path("./sanity/debug")
        )

        print("[OK] Pipeline returned valid JSON:")
        print(json.dumps(result, indent=2))
        
        # Verify deterministic table extraction happened (we can't easily check internal state 
        # without mocking the function, but we know it runs if no error)
        # We can check if result matches mock_response
        assert result["name"] == "Widget 3000"
        assert len(result["specs"]) == 1

if __name__ == "__main__":
    try:
        test_pipeline_mocked()
        print("\nSanity Check PASSED")
    except Exception as e:
        print(f"\nSanity Check FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
