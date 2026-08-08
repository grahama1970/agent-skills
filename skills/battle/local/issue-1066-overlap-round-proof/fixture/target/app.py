"""app - target.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

def import_zip(name: str) -> str:
    if '..' in name:
        return 'blocked'
    return 'ok'
