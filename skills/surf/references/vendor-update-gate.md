# Surf Vendor Update Gate

Schema: `surf.vendor_update_gate.v1`

Before syncing or promoting a new upstream `surf-cli` engine, the release packet
must include:

1. Pinned upstream repository and commit SHA, not a moving branch name.
2. Downstream patch inventory classified as general engine fix, provider
   workflow behavior, wrapper concern, obsolete workaround, or generated noise.
3. Vendored content identity hash from `vendor/surf-cli/VENDOR.lock.json`.
4. Extension build freshness result from `surf extension.fresh --json`.
5. Capability contract output from `surf capabilities --json`.
6. Focused regression suite output covering provider wrappers, exact-tab
   identity, stale-binding repair, lock behavior, and immutable receipts.
7. Rollback receipt naming the prior engine commit/hash and the command to
   restore it.

Do not close an upstream-sync ticket from package version alone. The acceptance
evidence is the update packet plus focused non-mocked regression output.
