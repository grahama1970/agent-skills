"""Public API surface definition for reality-check-sparta."""
# Public API surface for reality-check-sparta.
# Imported by __init__.py to populate __all__.

EXPORTS = [
    # Config
    "SPARTA_DIR", "MEMORY_DIR", "SPARTA_EXCEL", "SPARTA_WEBSITE",
    "CONVERGENCE_FILE", "SPARTA_TECHNIQUE_CATEGORIES",
    "EXPECTED_SPARTA_STRUCTURE", "SPACE_TERMINOLOGY",
    "EXPECTED_MITRE_ALIGNMENT", "SPACE_ATTACK_VECTORS",
    "SUSPICIOUS_GENERIC_PATTERNS", "EXPERT_QUESTIONS",
    "BRANDON_BAILEY_PERSONA", "DR_JAMES_PAVUR_EXPERTISE",
    "ANNEALING_SCHEDULE", "FIX_SUGGESTIONS", "VERIFICATION_TECHNIQUES",
    "LAYPERSON_INDICATORS", "PROJECT_MANAGER_INDICATORS",
    "EXPERT_INDICATORS", "TECHNICAL_JARGON", "TACTIC_KEYWORDS",
    # Annealing
    "get_annealing_thresholds", "should_continue_generation",
    # Data loading
    "get_db_copy",
    # Statistical tests
    "check_qra_stats", "check_sparta_alignment", "check_qra_structure",
    "check_marginal_qra_analysis", "check_coverage_gaps",
    "check_sparta_source_fidelity",
    # Adversarial
    "check_url_file_alignment", "check_url_knowledge_contamination",
    "check_qra_verbatim_grounding", "extract_technique_from_html",
    "verify_url_fresh", "verify_against_excel", "run_fresh_verification",
    # Brandon review
    "check_brandon_bailey_review", "check_persona_stratified_validation",
    # Convergence
    "track_convergence", "get_convergence_history", "analyze_convergence",
    "suggest_fixes",
    # Reporting
    "print_report", "print_fix_suggestions", "generate_client_report",
    "store_findings_in_memory", "run_status",
    # CLI
    "run_check", "run_iteration_loop", "run_convergence_analysis",
    "suggest_fixes_for_findings", "main",
]
