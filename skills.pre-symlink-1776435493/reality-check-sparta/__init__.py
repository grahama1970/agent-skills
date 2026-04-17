"""SPARTA QRA Reality Check - ADVERSARIAL data quality assessment.

Philosophy: trust nothing, verify everything. A PASS is hard to earn.
Modules: config, annealing, data_loader, statistical_tests, adversarial,
         brandon_review, convergence, reporting, cli.
"""

from config import *  # noqa: F401, F403
from annealing import *  # noqa: F401, F403
from data_loader import *  # noqa: F401, F403
from statistical_tests import *  # noqa: F401, F403
from adversarial import *  # noqa: F401, F403
from brandon_review import *  # noqa: F401, F403
from convergence import *  # noqa: F401, F403
from reporting import *  # noqa: F401, F403
from cli import *  # noqa: F401, F403
from _all import EXPORTS as __all__  # noqa: F401
