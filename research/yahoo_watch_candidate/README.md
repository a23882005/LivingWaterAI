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

The reference entry point `market_poll.py` now runs `original_rd_observer.py` on completed daily observations using the pinned original producer. Source status OBSERVED_DAILY_FORMULA AND original RunawayDown TRUE starts observation without requiring valuation. Its durable activation receipt keeps monitoring active across later FALSE/UNKNOWN; V82_MONITOR_STOP_SYMBOLS or the global enable flag provides manual stopping. Only active symbols fetch 5m reference bars. Routine checks, missing/unqualified quotes and stale observations are recorded in Actions logs, leaving the mailbox quiet. A Gmail risk alert is sent only after the pinned original daily observation is current for the expected completed exchange session, the original approved RunawayDown formula returns TRUE, and the observed source has a valid SHA256 receipt. Every alert remains REFERENCE_ONLY and formal_v82_executed=false. No new buy threshold or trade permission is introduced. Each symbol/completed-session risk alert has a fixed event ID and is deduplicated across 10-minute polls and changing intraday prices.

## Task consumer contract
Sender/recipient remain the authorized Gmail account. Newly sent subject lines are concise, positive and directly actionable, e.g. `[V82-WATCH] VT｜日線急跌警戒已觸發｜請檢查買單｜11/18 21:07`. Older dynamic titles and the legacy fixed subject remain valid historical messages for read-only task parsing.

The first lines of a new alert state exactly what was observed (original approved formula on a completed trading day's data), the observed session and an **exact order-check checklist**: unfilled limit price, quantity, GTC expiry and reserved cash; defer new orders pending the formal V82 safety, valuation and account decision. They now include the pinned original producer's completed-day close, previous close, day low, change percent, D1-D3 true codes, A1-A8 true codes, and the confirmed swing-low level/date when the unchanged original D2 crossing can be independently tied to that pivot. These are source *observations*, never account/permission fields. Absent figures or votes are explicitly marked missing; a 5m PRE quote never substitutes for daily close. Qualified intraday reference quotes appear as separate context, and OLD_OBSERVATION_NOT_CURRENT is explicitly labelled an expired/old value. Canonical JSON continues after the same marker; the new daily scalar fields are optional, so historical messages still parse. Missing/stale 5m quotes never become a market price or trigger a routine email.

The canonical JSON remains **unchanged** and follows the exact plain-text delimiter `--- LW_MARKET_JSON_V1 ---` on its own line. Production alerts are one `LW_MARKET_NOTICE_V1` item per asset/completed-session risk event, identified by `rd-daily-action-v1:<symbol>:<session>`. Consumers should verify sender, `[V82-WATCH]` prefix, original completed-session `rd_observation=TRUE`, and genuine GitHub run evidence; then parse the JSON after the delimiter. Continue accepting historical `LW_MARKET_BATCH_V1` and legacy preamble mail, verifying each item and excluding expired/test rows. Repeated polls, changed intraday bars and updated run IDs do not create new risk alerts for the same session.

Required metadata includes event_id, generated_at/observed_at, run_id/run_url, source, data_status, notice_kind, formal_v82_executed and valid_until. Market observations also carry quote_time, session and delay_seconds. TEST is not evidence; REFERENCE_ONLY cannot replace formal V82 daily inputs. Expired, missing or unqualified data remains UNKNOWN. Receiving a message never authorizes trading.

## Remaining real integration gates
Formal automatic activation needs the original producer running against qualified daily data; the existing qualification route is scoped and must not be generalized. Yahoo 5m does not establish daily/source/corporate-action qualification. Missing futures and true overnight coverage remain UNKNOWN. Formal rule content/version verification and genuine event occurrences must be supplied before any formal market signal can be sent. Do not call the reference workflow a completed V82 financial engine.

## Original RD runner verification
Real GitHub run 42763313261 passed: 55 candidate tests, 25 original source tests, and actual Yahoo -> unchanged original completed-session intake -> approved RD formula. VT and TSM reached 2026-11-09 daily observations (RD FALSE). 0050 correctly stayed UNKNOWN while 2026-11-10 final close was not yet available after the exchange close. SOXX stayed UNKNOWN due to a split event in the requested source window. This is a source/formula observation success, not full financial qualification.

Nineteen public tickers were separately observed locally: 16 reached the current completed US daily formula (11 FALSE, 5 UNKNOWN); 0050 had the pending-close limit, SOXX the split-window limit, and SGOV retained the original fixed-income route. This is not a verified inventory of all household holdings. Non-US/non-Taiwan calendars and fixed-income instruments are not silently mapped to US equity rules.

RunawayDown is a severe-downtrend condition. Using it alone will not detect every early-left opportunity. It only activates monitoring and never bypasses original safety or becomes permission to buy. A true predicate requires no valuation input, but a financial buy decision still requires the full original rule chain.

## Batch freshness correction
Production Gmail sends only one verified original completed-session RunawayDown observation per instrument and trading session, using `LW_MARKET_NOTICE_V1`. The former `LW_MARKET_BATCH_V1` consumer interface remains supported for previously sent mail. Reference price, quote timestamp, individual validity and data status remain in the JSON when available; old/closed-market observations remain in monitoring logs and never refresh the alert. The original persistent observation activation and outbox event receipts remain separate.

Watch activation receipts and mail receipts have distinct event namespaces. A persisted original-RD observation activation survives unknown data, restarts and SMTP uncertainty; it is not trading permission. `V82_MONITOR_STOP_SYMBOLS` pauses named symbols. Removing a symbol from that pause list resumes its previously activated observation; it does not erase prior activation. Evaluation order rotates with the workflow run number. If the time budget is exhausted, every remaining symbol gets a NOT_EVALUATED item rather than silently disappearing.

Validation must use the current `python research/yahoo_watch_candidate/run_tests.py` runner. Regression covers current completed-session and valid source receipts, UNKNOWN/FALSE silence, same-session intraday change deduplication, separate new-session alerts, safe mocked SMTP, and unchanged canonical JSON. Unit tests do not send real email; production cadence remains the previously approved 10-minute best-effort schedule.
