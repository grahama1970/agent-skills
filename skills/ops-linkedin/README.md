# ops-linkedin

`ops-linkedin` prepares LinkedIn work without automating outreach, bulk scraping, posts,
message/InMail sending, comments, applications, or unscoped third-party profile access. It converts typed JSON
requests into evidence-aware handoff packets, and it can export an editable JSON entry for
Graham's own LinkedIn profile from `RESUME.md`. It can also prepare bounded read-only
contact graph capture plans for named opportunity contacts after explicit authorization.

## Why it differs from browser-native LinkedIn skills

The open-source `quantumbyte31/linkedin-skills` project demonstrates a useful six-lane
router, but it drives LinkedIn through a Chrome extension and local DOM bridge. LinkedIn's
current User Agreement and Help Center prohibit unauthorized automated access, scraping,
and automated social actions. This implementation keeps the useful lane structure while
removing unbounded browser/session access and execution.

It is an engineering policy choice, not a representation that every possible use is
legally approved. The policy snapshot is dated and must be rechecked before expansion.

## Implemented lanes

- **Profile:** prepare evidence-bounded profile-field updates.
- **Explore:** prepare a manual search query and review plan.
- **Publish:** prepare text or image-post copy and attachment checks.
- **Interact:** prepare one comment, connection note, or message.
- **Lead generation:** prepare public-web research, manual review criteria, and bounded
  read-only contact graph capture plans for named opportunity contacts.
- **Content operations:** analyze user-provided/exported content and metrics.

Every outbound lane ends before LinkedIn send/connect/follow actions. Graham's own
profile has a separate JSON-first sync plan that requires explicit account-risk and
own-profile flags. Named opportunity contact graphs have a separate read-only plan that
requires explicit read-only authorization and account-risk flags.

## Quick start

```bash
cd skills/ops-linkedin
uv sync --extra dev

bash ./run.sh policy
bash ./run.sh status
bash ./run.sh prepare assets/examples/publish-post.json -o /tmp/linkedin-handoff.json
bash ./run.sh validate /tmp/linkedin-handoff.json
bash ./run.sh profile-entry-export \
  --resume-source ../../RESUME.md \
  --profile-url "https://www.linkedin.com/in/grahamanderson/" \
  -o /tmp/linkedin-profile-entry.json
bash ./run.sh profile-sync-plan \
  --entry-json /tmp/linkedin-profile-entry.json \
  --accept-account-risk \
  --own-profile-only \
  -o /tmp/linkedin-profile-sync.json
bash ./run.sh contact-graph-capture-plan \
  --opportunity "Moog Senior AI Engineer" \
  --target "George Small|Moog|https://www.linkedin.com/in/george-small-moog/" \
  --user-authorized-read-only \
  --accept-account-risk \
  -o /tmp/linkedin-contact-graph-plan.json
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
real CLI in positive and negative cases. Surf appears only as an emitted command plan for
the own-profile sync packet and the bounded named-contact graph capture packet.

## Current scope

Ready: local manifest validation, handoff creation, claim blocking, packet validation,
status/policy reports, editable own-profile JSON export, own-profile Surf sync planning,
bounded named-contact graph capture planning, and bounded human attestation.

Not implemented: generalized login checks, unscoped third-party LinkedIn browsing, search
execution, bulk profile retrieval, posting, likes, comments, connections, follows,
message/InMail sending, uploads, applications, or an official API adapter.
