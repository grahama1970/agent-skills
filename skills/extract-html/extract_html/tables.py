"""tables - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from io import StringIO

import pandas as pd
from loguru import logger


def extract_html_tables_to_json(html: str, *, max_tables: int = 20) -> Dict[str, Any]:
    """
    Deterministically extract HTML <table> elements using pandas.read_html.
    Produces a stable JSON representation.
    """
    try:
        dfs = pd.read_html(StringIO(html))  # lxml parser
    except ValueError:
        return {"tables": []}
    except Exception as e:
        logger.warning("pandas.read_html failed: {}", e)
        return {"tables": [], "error": str(e)}

    tables = []
    for i, df in enumerate(dfs[:max_tables]):
        # Convert to simple JSON with headers+rows
        headers = [str(c) for c in df.columns.tolist()]
        rows = df.astype(object).where(pd.notnull(df), None).values.tolist()
        tables.append(
            {
                "index": i,
                "headers": headers,
                "rows": rows,
                "source": {"type": "html_table", "index": i},
            }
        )
    return {"tables": tables}
