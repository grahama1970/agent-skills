"""Chart design example data for batch-learning into /memory.

Re-export shim -- examples split into chart_examples_good.py and
chart_examples_bad.py to stay under the 900-line file length limit.
"""

from chart_examples_bad import BAD
from chart_examples_good import GOOD

__all__ = ["GOOD", "BAD"]
