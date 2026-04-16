#!/usr/bin/env python3
"""
Persona Integration for create-movie

Provides seamless integration with the persona system:
- ContextEngineer: Persona-colored screenplay context
- TaxonomyVerifier: Bridge cinematography concepts to Federated Taxonomy bridges
- TTSClient: Voice narration generation (configurable per persona)
- EpisodicArchiver: Store creation sessions in memory

Implementation is split across:
- persona_integration_core.py: PersonaContext, PersonaIntegration, bridge augments, convenience funcs
- persona_integration_experts.py: PlatformExpert registry, CreativeTeam, ExpertDirectorReviewLoop
"""

from pathlib import Path
from typing import Optional

# Re-export all public names from sub-modules for backward compatibility
from persona_integration_core import (  # noqa: F401
    _find_project_root,
    _PROJECT_ROOT,
    PERSONA_PROJECT_PATH,
    MEMORY_PROJECT_PATH,
    PersonaContext,
    PersonaIntegration,
    BRIDGE_PROMPT_AUGMENTS,
    augment_prompt_with_bridges,
    get_bridge_examples,
    get_persona,
    enrich_screenplay_context,
    extract_bridges,
    generate_narration,
    generate_horus_narration,
    archive_session,
)

from persona_integration_experts import (  # noqa: F401
    PlatformExpert,
    PLATFORM_EXPERTS,
    MODEL_TRAINING_EXPERTS,
    get_training_expert,
    get_expert_for_platform,
    list_available_platforms,
    CreativeTeam,
    EXPERT_REVIEW_TEMPLATE,
    EXPERT_TO_DIRECTOR_TEMPLATE,
    DIRECTOR_APPROVAL_TEMPLATE,
    ExpertReview,
    DirectorApproval,
    ExpertDirectorReviewLoop,
)


if __name__ == "__main__":
    # Test the integration
    print("Testing Persona Integration...")

    persona = get_persona()
    print(f"Persona system available: {persona.available}")

    if persona.available:
        # Test context retrieval
        print("\nTesting screenplay context...")
        ctx = persona.get_screenplay_context("A dark siege with massive fortifications")
        print(f"  Bridges detected: {ctx.bridge_attributes}")
        print(f"  Context preview:\n{ctx.render()[:500]}")

        # Test bridge extraction
        print("\nTesting bridge extraction...")
        bridges = persona.extract_cinematography_bridges(
            "The fortress walls crumbled under precise artillery fire, "
            "each shot calculated to maximum effect."
        )
        print(f"  Extracted bridges: {bridges}")

        # Test prompt augmentation
        print("\nTesting prompt augmentation...")
        augmented = augment_prompt_with_bridges(
            "cinematic siege scene at sunset",
            ["Precision", "Resilience"]
        )
        print(f"  Augmented prompt: {augmented}")
    else:
        print("Persona system not available - running in fallback mode")
