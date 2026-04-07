"""Shadow-LEGO cascade wiring for /extract-pdf decision points."""

from extract_pdf.cascade.wiring import (  # noqa: F401
    get_header_runner, get_profile_runner, get_strategy_runner,
    log_extraction_decisions, log_header_decisions, log_shadow,
)
