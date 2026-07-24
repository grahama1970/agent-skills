# Vendored surf-cli copy

This tree is synced into `agent-skills/skills/surf/vendor/surf-cli` for the
`surf` skill.

Current engine target:

- Upstream repository: `https://github.com/nicobailon/surf-cli.git`
- Upstream tag: `v2.9.0`
- Upstream commit: `38e1ef4515bef0aaee4848a257fb237bad053f9d`

This is not a clean upstream copy. It includes a downstream compatibility
patchset for agent-skills WebGPT and provider-tab contracts, including:

- ChatGPT conversation max-length detection
- ChatGPT too-many-requests detection
- exported readiness helper for downstream WebGPT pre-submit checks
- exported sentinel/stable-stall response polling compatibility
- `chatgpt.extract` recovery support for orphaned/interrupted WebGPT submits
- `focus.state` command support for WebGPT background-mode proof
- `extension.ping` and `extension.reload` command support for skill-managed
  extension refresh
- `gemini_tab` and `kimi_tab` native provider commands used by the skill
  wrapper scripts
- no-activate provider-tab creation metadata for background proof
- Kimi capacity-busy detection that fails closed on provider overload messages
- provider-tab stderr metadata consumed by downstream wrapper scripts

Run `surf vendor.status --json` to inspect the recorded tree identity.
