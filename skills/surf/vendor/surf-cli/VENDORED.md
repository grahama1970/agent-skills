# Vendored surf-cli copy

This tree is synced into `agent-skills/skills/surf/vendor/surf-cli` for the
`surf` skill.

Current engine target:

- Upstream repository: `https://github.com/nicobailon/surf-cli.git`
- Upstream tag: `v2.9.0`
- Upstream commit: `38e1ef4515bef0aaee4848a257fb237bad053f9d`

This is not a clean upstream copy. It includes a small downstream compatibility
patchset for agent-skills WebGPT contracts, including:

- ChatGPT conversation max-length detection
- ChatGPT too-many-requests detection
- exported readiness helper for downstream WebGPT pre-submit checks
- exported sentinel/stable-stall response polling compatibility

Run `surf vendor.status --json` to inspect the recorded tree identity.
