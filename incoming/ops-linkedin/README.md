# ops-linkedin

> **Repository status:** staged under `incoming/ops-linkedin`. It is not an active repository capability until a separate promotion PR moves it to `skills/ops-linkedin` and registers its capability vocabulary entries.

`ops-linkedin` prepares LinkedIn work without automating LinkedIn. It converts a typed JSON
request into an evidence-aware handoff packet containing reviewed copy, explicit claim
sources, manual steps, negative automation guardrails, and bounded proof semantics.

## Why it differs from browser-native LinkedIn skills

The open-source `quantumbyte31/linkedin-skills` project demonstrates a useful six-lane
router, but it drives LinkedIn through a Chrome extension and local DOM bridge. LinkedIn's
current User Agreement and Help Center prohibit unauthorized automated access, scraping,
and automated social actions. This implementation keeps the useful lane structure while
removing browser/session access and execution.

It is an engineering policy choice, not a representation that every possible use is
legally approved. The policy snapshot is dated and must be rechecked before expansion.

## Implemented lanes

- **Profile:** prepare evidence-bounded profile-field updates.
- **Explore:** prepare a manual search query and review plan.
- **Publish:** prepare text or image-post copy and attachment checks.
- **Interact:** prepare one comment, connection note, or message.
- **Lead generation:** prepare public-web research and manual review criteria.
- **Content operations:** analyze user-provided/exported content and metrics.

Every lane ends before LinkedIn access.

## Quick start

```bash
cd incoming/ops-linkedin
uv sync --extra dev

bash ./run.sh policy
bash ./run.sh status
bash ./run.sh prepare assets/examples/publish-post.json -o /tmp/linkedin-handoff.json
bash ./run.sh validate /tmp/linkedin-handoff.json
bash ./sanity.sh
```

A blocked evidence-sensitive request is still written for review and exits with code `3`:

```bash
bash ./run.sh prepare assets/examples/profile-update-blocked.json \
  -o /tmp/blocked.json
```

After the human personally completes a ready action:

```bash
bash ./run.sh attest /tmp/linkedin-handoff.json \
  --actor "Graham" \
  --confirm-human-completed \
  -o /tmp/linkedin-completion.json
```

The completion packet says only that the named human attested to manual completion. It
retains `platform_verified: false`.

## Request example

```json
{
  "schema_version": "ops-linkedin.request.v1",
  "lane": "publish",
  "action": "post",
  "content": {
    "text": "A reviewed post draft."
  },
  "claims": [
    {
      "claim_id": "evidence-1",
      "text": "A factual statement used in the draft.",
      "status": "verified",
      "source_refs": ["path/to/local-receipt.json"]
    }
  ]
}
```

See `references/contracts.md` for the complete vocabulary and lifecycle.

## Development

```bash
uv run --extra dev pytest
uv run --extra dev ruff check src tests
bash ./sanity.sh
```

The source package intentionally has no HTTP, browser, WebSocket, cookie, or scraping
dependencies. `sanity.sh` statically rejects those implementation surfaces and runs the
real CLI in positive and negative cases.

## Current scope

Ready: local manifest validation, handoff creation, claim blocking, packet validation,
status/policy reports, and bounded human attestation.

Not implemented: login checks, LinkedIn browsing, search execution, profile retrieval,
posting, likes, comments, connections, messages, uploads, applications, or an official API
adapter.
