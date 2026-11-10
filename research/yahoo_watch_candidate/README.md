# Market observer isolation candidate

Read-only scaffolding, not an active scheduler or a V82 implementation. No network call, email, secrets, holdings, trading or production change is included.

Run `python -m unittest discover -s tests -v` in this directory. The 20 synthetic tests cover parse quality, incomplete bars, delay, missing data, deduplication keys and three-state monitor routing.

## Boundary
- `monitor_core.py` interprets Yahoo chart observations; not certified realtime or formal source qualification.
- `watch_router.py` consumes current formal L_price / RunawayDown evidence. A true observation starts monitoring, never permits a buy. Unknown data does not silently stop an active watch; stopping is manual.
- The expected rule hash, input authenticity, validity period and persistent previous state must be supplied by a trusted adapter. JSON flags alone are not authentication.
- `data_event_id` is a stable identifier, not a durable notification-outbox implementation.
- Calendar holiday/early-close eligibility, source adjustment evidence, authenticated formal predicate production, private persistent outbox and SMTP outcome reconciliation remain integration gates.
- Existing source-qualified daily technical producers must be reused. Five-minute Yahoo bars must never be substituted for daily V82 inputs. The existing scoped qualification adapter supports only its explicitly implemented symbols; expansion needs independent qualification.

## Deployment contract (not enabled)
A future independent workflow may poll every ten minutes; GitHub cron is best-effort, not a real-time guarantee. Existing full-history workflows must not be repurposed into full-history updates every ten minutes. Do not commit private snapshots or email bodies, expose them in logs/summary, or store them in publicly downloadable artifacts.

A private outbox must reserve event IDs before send, mark confirmed sends, and reconcile uncertain SMTP results before retry. Ephemeral caches cannot guarantee deduplication. Monitoring status is not trading permission; lack of a notification does not prove lack of a buying opportunity. No paid service or changed V82 threshold is part of this candidate.

## Tested notification and producer interfaces
`formal_adapter.py` projects the existing approved decision's `left_inputs.price_condition_at_least_one` and the original technical bridge's `native_technical_aggregation.runaway_down`; it never recalculates their formulas or exports account identities. Output hashes and source qualification receipts are mandatory, but must come from trusted original execution; JSON claims are not authentication.

`safe_notify.py` adds an allowlisted metadata-only message, no stdout/stderr/body logging, and a SQLite PENDING/SENT outbox. Pending is durably reserved before SMTP. Any uncertain delivery, including server acceptance followed by persistence failure, requires reconciliation rather than blind automatic resend. SMTP acceptance is not inbox-delivery proof. The caller must provide an independently verified private persistent filesystem; an ephemeral runner or publicly downloadable artifact is not acceptable. No real SMTP send or persistent service was enabled.

Run the tests as above: 33 synthetic tests. Data qualification, private persistent storage deployment, credential validity and inbox delivery still require real integration verification. The existing temporary shared-writer probe cleans itself up and must not be mistaken for an operating persistent outbox.

## Isolated private filesystem probe
`private_outbox_probe.py` is a Linux/POSIX server-ready synthetic probe, not an enabled service. It creates a NEW 0700 `.v82-watch-synthetic-RUN_ID` directory beneath an explicitly authorized non-public parent, refuses reuse, and leaves its synthetic recovery evidence in place. It uses `flock` plus SQLite transactions and does not invoke SMTP, read credentials, access existing DBs or print private paths/row bodies.

Example, only after verifying the target private parent: `python private_outbox_probe.py probe --parent VERIFIED_PRIVATE_PARENT --run-id UNIQUE_TEST_ID`.

Local verification: 12 competing processes produced exactly one reservation and 11 deduplications; forced process termination after committed PENDING retained PENDING on restart; SENT remained deduplicated; SQLite integrity check passed. Added rejection tests cover existing directories, public paths, symlinks and path traversal IDs. Total: 38 synthetic tests. These are LOCAL results, not Hostinger verification. The probe requires a trusted authenticated deployment path; do not expose secrets to untrusted PR jobs or repurpose a production/TEMP DB.
