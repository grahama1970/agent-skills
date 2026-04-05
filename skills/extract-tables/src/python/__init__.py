"""extract-tables: Composable PDF table extraction (Rust + compiled Python)."""
from .extract_tables import read_pdf
from .models import Table, Cell, ExtractionResult
