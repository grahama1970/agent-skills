# LinkedIn policy and upstream adaptation

Policy snapshot checked: 2026-08-02

## Official sources

- LinkedIn User Agreement: https://www.linkedin.com/legal/user-agreement
- LinkedIn Help, "Violating Tools":
  https://www.linkedin.com/help/linkedin/answer/a1339701

At the snapshot date, the User Agreement was effective November 3, 2025. Section 8.2
prohibits bots and other unauthorized automated methods for access and social actions,
including messages, posts, comments, likes, shares, and similar engagement. LinkedIn's Help
Center also says unauthorized third-party tools that scrape, modify, or automate the site
are not permitted and can lead to account restrictions.

This file paraphrases the official material. Re-read the live sources before changing the
boundary because terms, approved products, and API programs can change.

## Upstream project assessed

- Repository: https://github.com/quantumbyte31/linkedin-skills
- Reddit announcement:
  https://www.reddit.com/r/LangChain/comments/1smun46/built_an_opensource_linkedin_toolskill_for_ai/
- License stated by upstream: MIT

Useful upstream ideas:

- one top-level skill router;
- six lanes for auth/profile context, exploration, publishing, interaction, lead generation,
  and content operations;
- a unified CLI;
- structured output;
- confirmation before consequential actions;
- centralized contracts and selectors.

Ideas intentionally rejected here:

- Chrome extension control;
- local WebSocket bridge to LinkedIn DOM;
- reading the logged-in session;
- feed/profile/search extraction;
- automated posts, comments, likes, connection requests, or messages;
- human-behavior simulation and selector maintenance.

Using a real browser or making automation resemble an ordinary user does not make the
method authorized. Frequency limits also do not resolve the underlying authorization issue.

## Bounded opportunity contact graph allowance

Operator update: when Graham explicitly authorizes it for a named opportunity, the
project agent may prepare and execute a bounded read-only contact graph capture plan
against Graham's own authenticated LinkedIn session. The only permitted purpose is to
identify relevant contacts for that opportunity and record visible relationship evidence:
target URL, name, title/company/location headline, visible degree, visible mutual names
if shown, and screenshot/artifact references.

This is not an outreach or connection authorization. The agent must not connect, follow,
react, post, apply, save, or send any message/InMail. The agent may prepare a relevant
InMail/message draft as a local handoff packet; sending remains a separate human action
and outbound roundtable-gated workflow.

The capture must stay small and named-target based. It must not enumerate a contact
database, inspect hidden browser state, read cookies/tokens/local storage, bypass platform
controls, or collect unrelated feed/search/profile data.

No upstream code is vendored in this skill. The lane vocabulary is an independently
implemented organizational adaptation.

## Expansion gate

Do not add any LinkedIn network or browser implementation until all of these are present:

1. Exact intended operations and user class.
2. Official authorization evidence for those operations.
3. Approved authentication and scopes.
4. Data minimization, retention, deletion, and audit rules.
5. Security review and adversarial tests.
6. Live receipts that prove only the authorized scope.
7. Updated SKILL.md, project knowledge, policy date, and non-claims.

Without those artifacts, the correct state is `NOT_IMPLEMENTED`, not aspirational support.
For the bounded opportunity contact graph allowance, those artifacts are represented by
`ops-linkedin.contact_graph_capture_plan.v1` plus the later
`monitor_opportunities.linkedin_contact_graph_evidence.v1` browser receipt.
