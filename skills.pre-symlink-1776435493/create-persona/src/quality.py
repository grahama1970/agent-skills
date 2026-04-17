#!/usr/bin/env python3
"""
Persona quality assessment, validation, and improvement.

Provides iterative debugging capabilities similar to /table-lab:
- Validate persona responses against ground truth
- Diagnose gaps in knowledge/connectivity
- Improve personas with convergence loop
- Audit batch quality with scoring

This is a thin assembler that re-exports from split modules:
- quality_metrics: PersonaQualityScore dataclass
- quality_diagnose: diagnose_persona
- quality_validate: ValidationTest, validate_persona, validate_simulacrum
- quality_improve: ImprovementResult, improve_persona
- quality_audit: AuditReport, SimulacrumBatchResult, validate_and_improve_batch, audit_personas
"""

# Re-export all public API from sub-modules
from .quality_metrics import PersonaQualityScore

from .quality_diagnose import diagnose_persona

from .quality_validate import (
    ValidationTest,
    validate_persona,
    validate_simulacrum,
)

from .quality_improve import (
    ImprovementResult,
    improve_persona,
)

from .quality_audit import (
    AuditReport,
    SimulacrumBatchResult,
    validate_and_improve_batch,
    audit_personas,
)

__all__ = [
    "PersonaQualityScore",
    "diagnose_persona",
    "ValidationTest",
    "validate_persona",
    "validate_simulacrum",
    "ImprovementResult",
    "improve_persona",
    "AuditReport",
    "SimulacrumBatchResult",
    "validate_and_improve_batch",
    "audit_personas",
]
