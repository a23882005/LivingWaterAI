# Isolated Yahoo observation and notification integration

This candidate does not change or execute the complete V82 strategy. No trading, account holdings or allocation inputs are included.

## Verified
- `python run_tests.py`: 47 unittest + 8 public-state tests pass locally.
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

`yahoo-reference-monitor.yml` is a main-only candidate schedule at minutes 3,13,23,33,43,53, enabled by the authorized main-branch deployment; set repository variable V82_REFERENCE_MONITOR_ENABLED=false or disable this workflow to pause it. It is not active merely because this PR exists. Existing schedules are unchanged. GitHub cron is best-effort; executions can be delayed or lost, and pending concurrency jobs can be replaced.

The reference entry point `market_poll.py` now runs `original_rd_observer.py` on completed daily observations using the pinned original producer. Source status OBSERVED_DAILY_FORMULA AND original RunawayDown TRUE starts observation without requiring valuation. Its durable activation receipt keeps monitoring active across later FALSE/UNKNOWN; V82_MONITOR_STOP_SYMBOLS or the global enable flag provides manual stopping. Only active symbols fetch 5m reference bars. An inactive FALSE emits no email; missing/unqualified data may emit a deduplicated health notice. Every notice remains REFERENCE_ONLY and formal_v82_executed=false. It DOES NOT claim a complete V82 buying-opportunity engine. Source-quality states repeat at most once per symbol/status/UTC day; same-day recurrence is intentionally suppressed. No new buy or decline threshold is invented.

## Task consumer contract
Sender and fixed subject must match the authorized Gmail account and `[V82-WATCH] Market observation (not a buy instruction)`.
Body JSON schema is LW_MARKET_NOTICE_V1. Required metadata includes event_id, generated_at/observed_at, run_id/run_url, source, data_status, notice_kind, formal_v82_executed and valid_until. Market observations also carry quote_time, session and delay_seconds. TEST is not evidence; REFERENCE_ONLY cannot replace formal V82 daily inputs. Expired, missing or unqualified data remains UNKNOWN. Receiving a message never authorizes trading.

## Remaining real integration gates
Formal automatic activation needs the original producer running against qualified daily data; the existing qualification route is scoped and must not be generalized. Yahoo 5m does not establish daily/source/corporate-action qualification. Missing futures and true overnight coverage remain UNKNOWN. Formal rule content/version verification and genuine event occurrences must be supplied before any formal market signal can be sent. Do not call the reference workflow a completed V82 financial engine.

## Original RD runner verification
Real GitHub run 42763313261 passed: 55 candidate tests, 25 original source tests, and actual Yahoo -> unchanged original completed-session intake -> approved RD formula. VT and TSM reached 2026-11-09 daily observations (RD FALSE). 0050 correctly stayed UNKNOWN while 2026-11-10 final close was not yet available after the exchange close. SOXX stayed UNKNOWN due to a split event in the requested source window. This is a source/formula observation success, not full financial qualification.

Nineteen public tickers were separately observed locally: 16 reached the current completed US daily formula (11 FALSE, 5 UNKNOWN); 0050 had the pending-close limit, SOXX the split-window limit, and SGOV retained the original fixed-income route. This is not a verified inventory of all household holdings. Non-US/non-Taiwan calendars and fixed-income instruments are not silently mapped to US equity rules.

RunawayDown is a severe-downtrend condition. Using it alone will not detect every early-left opportunity. It only activates monitoring and never bypasses original safety or becomes permission to buy. A true predicate requires no valuation input, but a financial buy decision still requires the full original rule chain.

## Batch freshness correction
Active observations are mailed as one `LW_MARKET_BATCH_V1` envelope per polling run at most. Each item retains its own quote timestamp, observation timestamp, quality and `valid_until`. A new completed source bar changes the public data fingerprint even if price stays equal; reruns with identical source data do not resend. Unknown/closed-market data is never relabeled current merely to refresh mail. Missing-source health fingerprints are day-scoped. Notifications may therefore expire when no newer source data exists; Tasks must return UNKNOWN rather than reuse stale mail.

Watch activation receipts and mail receipts have distinct event namespaces. A persisted original-RD observation activation survives unknown data, restarts and SMTP uncertainty; it is not trading permission. `V82_MONITOR_STOP_SYMBOLS` pauses named symbols. Removing a symbol from that pause list resumes its previously activated observation; it does not erase prior activation. Evaluation order rotates with the workflow run number. If the time budget is exhausted, every remaining symbol gets a NOT_EVALUATED item rather than silently disappearing.

Validation: 57 unittest + 8 public-state tests pass locally, including a two-symbol three-poll test (same bar twice, then a new bar) producing exactly two batch messages with two rows each. No real mail is sent by this unit test. The authorized deployment activates on main and performs a first push-triggered observation; candidate branch is never a running production schedule.
