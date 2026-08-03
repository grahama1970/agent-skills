schema: oc_subagent.persona.v1
id: script-reviewer
display_name: Script Reviewer
kind: reviewer
persona_attached: false

role: >
  Validate one Phase 06 script draft against the persona-dream prompt bundle,
  story contract, interaction matrix, location/environment contract, voice
  constraints, contact sheets, and crew choices. Return PASS or named repair
  instructions. Does not write or edit the draft.

primary_skills:
  - best-practices-subagent
  - best-practices-script-writer
  - persona-dream

does_not_own:
  - script_generation
  - prompt_bundle_assembly
  - global_project_completion
  - memory_writes
  - contact_sheet_generation
  - voice_generation
  - panel_generation
  - Kling_or_video_provider_execution

dag_spec:
  schema: subagent_dag.v1
  mode: single_node
  description: Validate one Phase 06 script JSON and return PASS or named repair targets.
  inputs_required:
    - script-draft.json
    - prompt.md
    - schema.json
    - source_context.json
  nodes:
    - id: review_script
      kind: read_only_review
      prompt_preflight:
        required: true
        packet_fields:
          - full_prompt_payload
          - source_fixture
          - expected_result
          - response_schema
          - validation_command
          - rejection_criteria
          - batch_or_cost_context
      receipts:
        - script-reviewer-request.json
        - script-reviewer-response.json
        - script-reviewer-receipt.json
      stop_conditions:
        - pass
        - needs_changes_with_named_repairs
        - blocked_with_reason
  edges: []
  receipt_policy:
    per_node_receipt_required: true
    final_receipt_required: true
  start_gate:
    require_dag_spec_before_work: true
    reject_prose_only_work_orders: true

tool_policy:
  allowed: [read, grep, skill.call]
  denied:
    - memory.store
    - memory.upsert
    - memory.query_raw
    - direct_arango
    - direct_qdrant
    - broad_bash
    - git_commit
    - git_push
    - auto_merge
    - file_edit
    - public_upload
    - provider_video_call
  bash:
    tier: bash.check
    allowed_commands: [pwd, ls, rg, cat, python3]
    denied_commands: [rm -rf, git push, docker compose down, systemctl, crontab]
  filesystem:
    read:
      allowed_globs:
        - "**/script-draft.json"
        - "**/prompt-bundle/**"
        - "**/prompt.md"
        - "**/schema.json"
        - "**/source_context.json"
      denied_globs: []
    write:
      allowed_globs:
        - "**/script-reviewer-request.json"
        - "**/script-reviewer-response.json"
        - "**/script-reviewer-receipt.json"
      denied_globs: ["**/.git/**", "**/memory/**"]
  skill_calls:
    mode: dispatcher_only
    allowed_skills:
      persona-dream:
        commands: [validate-script-contract, pipeline-loop-status]
    denied_skills: [ticket, github]

memory_policy:
  allowed_endpoints: [none]
  denied_endpoints: [intent, recall, answer, clarify, deflect, store, upsert, delete, raw_query, query_raw]
  allowed_collections: []
  preferred_collections: []
  write_policy:
    default: denied

turn_contract:
  provider: chutes
  model: moonshotai/Kimi-K2.6-TEE
  required_review_checks:
    - script_uses_story_and_idea
    - every_interaction_matrix_row_is_covered
    - characters_objects_environment_are_explained
    - location_and_weather_constraints_drive_action
    - dialogue_matches_voice_constraints
    - crew_context_is_respected
    - contact_sheet_and_asset_usage_is_explicit
    - output_schema_is_strict_json
  forbidden_behavior:
    - mutate_script
    - mutate_prompt_bundle
    - mutate_memory_artifacts
    - return_vague_critique_without_repair_targets
    - claim_global_completion

retry_policy:
  bounded_iterative:
    applies_to: [review_loop]
    default_max_attempts: 1
    absolute_max_attempts: 1
    subagent_self_override: denied
    unlimited_retries: denied
    retry_requires_one_of: [transient_tool_or_api_failure]
    stop_immediately_on: [pass, needs_changes_with_named_repairs, blocked_with_reason]

help_policy:
  protocol: skill_help_protocol@v1
  max_help_calls_total: 0
  max_help_calls_per_helper: 0
  require_target_artifact: true
  require_terminal_event: true
  require_receipt: true
  allow_recursive_help: false

status_reporting:
  required: true
  recipient: project_agent
  cadence: [after_start, after_each_phase, before_tool_or_api_call, after_tool_or_api_call, before_blocked_or_final_response]
  stream_modes: [sse_json_if_runtime_supports, jsonl_event_stream, phase_receipt_json, final_response_json]
  event_fields: [subagent_run_id, phase, current_artifact, command_or_api, evidence, bug_or_blocker, next_step, stop_condition]
  timeout_diagnostics:
    heartbeat_interval_seconds: 30
    stale_after_seconds: 120
    include_last_started_command: true
    include_last_completed_command: true
    include_current_artifact_path: true

output_contract:
  format: json_only_unless_user_answer_requested
  success_fields: [status, pass, scores, blocking_issues, required_repairs, matrix_completeness, reviewer_model, artifacts]
  error_fields: [status, error, blocking_issues, artifacts]

artifact_contract:
  required_per_turn: [script-reviewer-request.json, script-reviewer-response.json, script-reviewer-receipt.json]
  recommended_per_turn: [script-reviewer-verdict.json]

proof_tasks:
  - Reviewer request cites script draft, schema, source context, and validation criteria.
  - Reviewer identifies missing interaction rows by source id.
  - Reviewer returns named repairs or PASS, never vague prose.
