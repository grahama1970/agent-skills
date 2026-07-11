# Sprite atlas repair policy

- Repair geometry only. Never fabricate missing frames by duplicating art.
- Missing required frames -> `BLOCKED_MISSING_FRAMES` + `regeneration-work-order.json`.
- Ambiguous mapping -> `REVIEW_REQUIRED` / `BLOCKED_AMBIGUOUS_MAPPING`; edit `mapping.approved.json` and rerun repair.
- Overflow after common-scale normalization -> `BLOCKED_FRAME_OVERFLOW`.
- Promotion requires receipt status `PASS_NATIVE` or `PASS_REPAIRED` and `validation.json.passed=true`.
- Named-frame patches require every planned replacement, full named-frame
  validation, and full runtime validation. A `PASS_FRAME_PATCH` receipt is
  promotable; partial or blocked patch receipts are not.
- Fixed-grid atlases are generated compatibility outputs. Prefer named frame
  files as authoring truth and never edit unrelated atlas cells during repair.
