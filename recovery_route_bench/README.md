# RecoveryRoute-Bench source audit

Source: AgenticFlict v2, Zenodo record 20118379 (CC-BY-4.0). The archive checksum was verified before this audit.

- PRs: 142,652; conflicting: 29,609.
- Conflicting PR states: CLOSED=23,197, MERGED=55, OPEN=6,357.
- Conflicting PRs with `merged_at`: 55.
- Conflict regions: 336,380; both full-text sides present: 0; both short previews present: 253,777.

## Repository reconstruction

Repository histories were reconstructed for 16 of the 17 repositories carrying
merged conflicting PRs. This covers 53 of 55 PRs and 10,348 of 10,359 conflict-file
records; `ignazio-ingenito/baialupo.com` is no longer publicly accessible. All base,
head, and merge commits referenced by the 53 accessible PRs were found.

The resolved tree matches the simulated base for 99 records, the agent head for
7,879, and neither side for 132; 16 have identical states on all sides. Another
2,222 paths are absent from all three trees and are excluded as non-resolvable
archive records. File absence on only one side is treated as a real add/delete
state, not as missing history.

`merged_conflict_manifest.csv` is the archive join,
`blob_resolution_audit.csv` contains the tree evidence, and
`reconstruction_summary.json` contains coverage counts. Tree equality is evidence
about which file state survived, not an `abandon` / `adapt` / `escalate` label.

`adjudication_sample.csv` is a deterministic 30-item review sheet, balanced across
exact-base, manual/combined, and exact-head evidence. Human route, confidence,
notes, and exclusion fields remain blank. Machine guesses are isolated in
`adjudication_machine_hypotheses.csv` so the first review can remain blind; they
must not be joined until labels are frozen. See `ANNOTATION_GUIDE.md`.

## Gate status

The archive does not contain an `abandon` / `adapt` / `escalate` outcome, resolved file content, revert link, or contested-resolution field. PR state is not a valid substitute: a closed-unmerged PR can be dropped for reasons unrelated to its conflict, and an open PR is right-censored rather than escalated. Only 55 conflicting PRs carry `merged_at`, and even those require repository history to distinguish adaptation from a manual merge resolution.

The repository-history dependency is now resolved for every accessible merged PR,
but Gate S3 remains open. An independent reviewer must label the 30-item sheet using
the resolved diff plus PR reverts/discussion. Only after agreement with the machine
hypotheses is measured may those rules be expanded and the §5.8 routing ceiling be
fit. Fitting on raw tree equality would silently substitute a proxy for the outcome.
