# S3 adjudication guide

Label `adjudication_sample.csv` without opening
`adjudication_machine_hypotheses.csv`. Inspect the PR description, the sampled
file using its corresponding blind packet in `adjudication_packets/`, and any
subsequent revert or contested discussion. Each packet contains the base-to-head
and head-to-merge diff; `blob_resolution_audit.csv` retains the full commit and
blob provenance.

- `abandon`: the agent-head objective was already subsumed or was deliberately
  dropped from the accepted resolution.
- `adapt`: the objective survives in a rewritten or combined form on the newer
  base.
- `escalate`: accepting the objective required rejecting a peer-side invariant,
  or a later revert/discussion records a substantive contract dispute.
- Exclude the item when the objective or losing side cannot be identified, the
  row is generated/bulk-sync noise, or the evidence does not distinguish routes.

Do not infer `escalate` merely because the merge tree equals the agent head, or
`adapt` merely because it differs from both sides. Record `high`, `medium`, or
`low` confidence and a short evidence note. Freeze the human columns before
joining the machine-hypothesis file and measuring agreement. A second blinded
reviewer is required for the claimed human upper bound.
