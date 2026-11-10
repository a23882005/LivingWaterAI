# Isolated Yahoo observation and notification integration

This candidate does not change or execute the complete V82 strategy. No trading, account holdings or allocation inputs are included.

## Verified
- `python run_tests.py`: 41 unittest + 8 public-state tests pass locally.
- GitHub synthetic CAS probe run 42755330078 passed: two contenders, one reservation, readback, restart deduplication, uncertain-write retention; actual emails zero.
- Gmail TEST smoke run 42755548047 passed SMTP acceptance; inbox confirmation must be checked separately. TEST messages are never market signals. Earlier smoke run 42755500652 failed before sending due to a metadata allowlist mismatch, fixed before the successful run.
- Local private SQLite/flock probe also passes 12-process contention and interruption/restart. This is NOT a Hostinger deployment claim.

## Interfaces
- `monitor_core.py`: Yahoo completed 5m observations, not certified realtime/formal daily data.
- `formal_adapter.py`: projects the original approved decision's price condition and original technical bridge's runaway_down. No formula duplication; trusted source receipts and producer output hashes are required. JSON flags alone are not authentication.
- `watch_router.py`: existing formal L_price / RunawayDown TRUE starts observation, never buy permission; UNKNOWN does not silently stop an active watch; stopping is manual.
- `github_json_outbox.py`: public receipt JSON contains ONLY opaque event hashes and PENDING/SENT. Contents API SHA compare-and-swap + readback reserves before send. No account, holdings, recipient, body or credential is stored in the JSON.
- `safe_notify.py`: allowlisted metadata-only notice, no private body logging. SMTP acceptance is not inbox-delivery proof. Any uncertain send remains PENDING and requires reconciliation, not blind retries.

## Workflow boundaries
`yahoo-watch-receipt-probe.yml` and `yahoo-watch-gmail-smoke.yml` run only from their named owner-controlled candidate branch push, not pull_request events. The former never receives Gmail credentials; the latter sends fixed TEST content only.

`yahoo-reference-monitor.yml` is a main-only candidate schedule at minutes 3,13,23,33,43,53, guarded by repository variable V82_REFERENCE_MONITOR_ENABLED=true. It is not active merely because this PR exists. Existing schedules are unchanged. GitHub cron is best-effort; executions can be delayed or lost, and pending concurrency jobs can be replaced.

The reference entry point `market_poll.py` can fetch configured public symbols (default 0050.TW,VT,SOXX,TSM), report quote time/session/delay, and deliver deduplicated pipeline-health notices. Every notice says REFERENCE_ONLY, formal_v82_executed=false, FORMAL_AUTOSTART_BLOCKED_UNKNOWN. It DOES NOT claim the requested full-strategy automatic buying-opportunity monitor is ready. Source-quality states repeat at most once per symbol/status/UTC day; same-day recurrence is intentionally suppressed. No new buy or decline threshold is invented.

## Task consumer contract
Sender and fixed subject must match the authorized Gmail account and `[V82-WATCH] Market observation (not a buy instruction)`.
Body JSON schema is LW_MARKET_NOTICE_V1. Required metadata includes event_id, generated_at/observed_at, run_id/run_url, source, data_status, notice_kind, formal_v82_executed and valid_until. Market observations also carry quote_time, session and delay_seconds. TEST is not evidence; REFERENCE_ONLY cannot replace formal V82 daily inputs. Expired, missing or unqualified data remains UNKNOWN. Receiving a message never authorizes trading.

## Remaining real integration gates
Formal automatic activation needs the original producer running against qualified daily data; the existing qualification route is scoped and must not be generalized. Yahoo 5m does not establish daily/source/corporate-action qualification. Missing futures and true overnight coverage remain UNKNOWN. Formal rule content/version verification and genuine event occurrences must be supplied before any formal market signal can be sent. Do not call the reference workflow a completed V82 financial engine.
