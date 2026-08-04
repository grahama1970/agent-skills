# ops-linkedin

`ops-linkedin` prepares LinkedIn work without automating outbound LinkedIn actions. It can
capture one human-authorized LinkedIn Jobs/opportunity tab as read-only local evidence for
`monitor-opportunities`, and it converts typed JSON requests into evidence-aware handoff
packets containing reviewed copy, explicit claim sources, manual steps, negative action
guardrails, and bounded proof semantics.

## Why it differs from browser-native LinkedIn skills

The open-source `quantumbyte31/linkedin-skills` project demonstrates a useful six-lane
router, but it drives LinkedIn through a Chrome extension and local DOM bridge. LinkedIn's
current User Agreement and Help Center prohibit unauthorized automated access, scraping,
and automated social actions. This implementation keeps the useful lane structure while
limiting browser use to explicit, human-authorized, read-only opportunity capture and
removing LinkedIn execution.

It is an engineering policy choice, not a representation that every possible use is
legally approved. The policy snapshot is dated and must be rechecked before expansion.

## Implemented lanes

- **Opportunity:** capture one human-authorized LinkedIn Jobs/opportunity tab into local
  evidence for downstream ranking.
- **Profile:** prepare evidence-bounded profile-field updates.
- **Explore:** prepare a manual search query and review plan.
- **Publish:** prepare text or image-post copy and attachment checks.
- **Interact:** prepare one comment, connection note, or message.
- **Lead generation:** prepare public-web research and manual review criteria.
- **Content operations:** analyze user-provided/exported content and metrics.

Every outbound/action lane ends before LinkedIn access. The opportunity lane may read one
already-open human-authorized tab and must stop after writing local evidence.

## Quick start

```bash
cd skills/ops-linkedin
uv sync --extra dev

bash ./run.sh policy
bash ./run.sh status
bash ./run.sh capture-opportunity-tab \
  --tab-id 837367508 \
  --human-authorized \
  --output /tmp/linkedin-opportunity-evidence.json
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

The source package intentionally has no HTTP client, WebSocket, cookie, credential, or
LinkedIn action dependencies. Surf is invoked only by the explicit
`capture-opportunity-tab` command. `sanity.sh` statically rejects direct network/browser
implementation surfaces and runs the real CLI in positive and negative cases.

## Current scope

Ready: authorized read-only opportunity capture, local manifest validation, handoff
creation, claim blocking, packet validation, status/policy reports, and bounded human
attestation.

Not implemented: login checks, broad LinkedIn browsing/search execution, profile
retrieval, posting, likes, comments, connections, messages, uploads, applications, or an
official API adapter.
