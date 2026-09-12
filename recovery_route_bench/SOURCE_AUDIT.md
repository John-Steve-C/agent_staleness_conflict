# RecoveryRoute-Bench source audit

Source: AgenticFlict v2, Zenodo record 20118379 (CC-BY-4.0). The archive checksum was verified before this audit.

- PRs: 142,652; conflicting: 29,609.
- Conflicting PR states: CLOSED=23,197, MERGED=55, OPEN=6,357.
- Conflicting PRs with `merged_at`: 55.
- Conflict regions: 336,380; both full-text sides present: 0; both short previews present: 253,777.

## Gate status

The archive does not contain an `abandon` / `adapt` / `escalate` outcome, resolved file content, revert link, or contested-resolution field. PR state is not a valid substitute: a closed-unmerged PR can be dropped for reasons unrelated to its conflict, and an open PR is right-censored rather than escalated. Only 55 conflicting PRs carry `merged_at`, and even those require repository history to distinguish adaptation from a manual merge resolution.

Therefore the routing ceiling cannot yet be estimated from AgenticFlict alone. The next valid S3 step is to reconstruct selected repositories at `base_oid`, `head_oid`, and the eventual resolution commit; derive candidate labels from the resolved content and reverts/discussion; then validate them on a hand-labelled subset before fitting §5.8 features. `source_audit.json` records the exact schema and counts that establish this dependency.
