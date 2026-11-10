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
