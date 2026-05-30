# Vendored surf-cli

Embry ships a fork of [grahama1970/surf-cli](https://github.com/grahama1970/surf-cli)
inside the `/surf` skill.

| Path | Purpose |
|------|---------|
| `vendor/surf-cli/` | Committed source |
| `vendor/surf-cli/VENDOR.lock.json` | Last sync commit + metadata |
| `vendor/fork.json` | Fork URL, branch, local dev path, rsync excludes |
| `vendor/surf-cli/node_modules/` | Local install (gitignored) |
| `vendor/surf-cli/dist/` | Local build (gitignored) |

**Update:** `surf vendor.sync --build --reload`  
**Status:** `surf vendor.status`
