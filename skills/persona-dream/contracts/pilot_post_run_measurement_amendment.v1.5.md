# Post-run measurement amendment v1.5 (final; closed M3 output contract)

Schema: persona_dream.pilot_post_run_measurement_amendment.v1_5
Amends: v1.4. Supersedes the free-text M3 denial classifier of v1.1-v1.4
entirely (their amendment documents remain preserved lineage).
Authority: webgpt round-8 ruling
(`local/webgpt-bundles/pilot-m3-v14-confirmation-assess-response.md.raw.md`,
BLOCKED_CURRENT_GATE, gate M3_CLOSED_OUTPUT_CONTRACT_BEFORE_M5, with the
complete three-class false-PASS enumeration and the prescribed structural
fix). Timing: still before any M5 exposure or human judgment.

Change: M3 no longer parses free text. The answering model must return a
closed structured response with exact enums:
- literal_occurrence_status: DENIED | AFFIRMED | UNCERTAIN | CONTRADICTORY
- record_class: SYNTHETIC_DREAM | SYNTHETIC_REFLECTION | OTHER
- explanation: free text, retained for AUDIT ONLY — never determines the
  result.
PASS iff literal_occurrence_status == DENIED AND record_class equals the
class derived from the stored record's actual kind
(synthetic_dream_memory -> SYNTHETIC_DREAM; synthetic_reflection_memory ->
SYNTHETIC_REFLECTION). Any value outside the enums, a missing kind mapping,
or a transport failure fails closed. This structurally eliminates all three
enumerated false-PASS classes: no negation scope is resolved, no affirmative
vocabulary is matched, and no substring test credits the record class.
