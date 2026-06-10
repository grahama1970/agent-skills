# WebGPT delivery rules (review-page → ask)

## Boundary

- **`/review-page`** builds `REVIEW_PACKET.md`, `review-bundle.zip`, and `review_page.gate.v1.json`.
- **`$ask webgpt`** owns the WebGPT call (`call_webgpt` → `surf webgpt.submit`), artifacts, tab binding, and rate limits.

Do not call `surf webgpt.submit` from `/review-page`.

## Packet build

```bash
review-page/run.sh run-ti --page coverage --capture-suffix -r2   # optional
review-page/run.sh build --page coverage --capture-dir <captures>
review-page/run.sh package --page coverage --round-label 2       # JSON manifest for ask
```

## Ask adjudication

```bash
cd ~/.pi/skills/ask
./run.sh ask webgpt "/review-page coverage round 2" \
  --webgpt-project sparta-explorer-review \
  --once --oracle-iterations 1
```

Ask reads the package manifest, attaches `review-bundle.zip` (≤5 files: md + up to 4 PNG), and submits the adjudication prompt.

## Fail closed

When `review_page.gate.v1.json` has `ask_blocked: true`, `$ask webgpt /review-page` stops before WebGPT unless `--force` is in the query.

## Do not

- Batch multiple Explorer pages in one WebGPT call.
- Claim screenshots in the inventory that are not in the zip attach set.
- Use raw `$surf webgpt.submit` for normal page review (bypasses ask artifacts).
