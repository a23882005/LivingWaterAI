# Nasdaq 23H candidate compatibility — v0.1

Base: PR59 `3f7ea0dcd2963ae55598ffa90b36893ed47cc9bb`. Candidate branch: `family/nasdaq-23h-compat-20261206`, stacked on `family/w8-complete-04-joseph-mou`. This branch implements source-bound session interpretation and safe daily-input separation. It does not activate an exchange, broker route, data feed or account, and it does not change the V82 strategy. Production HOLD; Trade NONE; full financial PASS 0; real Cycle 0.

Authority: [middle PM contract](https://docs.google.com/document/d/1mhoLviSU3fQAVmPZyJwv2Masxkw1R51zyh7OM31GFQk/edit) and [dispatch](https://github.com/a23882005/LivingWaterAI/pull/59#issuecomment-6677269409). Existing scoped PASS, daily B0/ledger math, M1/M8, modes/stages, 49/13 fields, pending-order accounting, SELL and PR60 layouts remain unchanged.

## Official sources and live-status limits

- [SEC 34-105199](https://www.sec.gov/files/rules/sro/nasdaq/2026/34-105199.pdf): approved rule structure, holidays and early closures; Night operation has additional SIP readiness and rule-filing prerequisites.
- [Nasdaq ETA2026-46](https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2026-46): announced December 6, 2026, 21:00 ET launch, night-to-next-business-day attribution and exchange-book cancellation at 04:00. Calendar dates are not permission to trade.
- [Nasdaq DN2026-8](https://www.nasdaqtrader.com/TraderNews.aspx?id=DN2026-8): independent night engine/feed and separate connectivity. Existing daytime feeds do not establish night-feed coverage.
- [Nasdaq FAQ](https://www.nasdaq.com/newsroom/nasdaq-explains-what-is-23-5-trading): 20:00–21:00 maintenance, Sunday-night through Friday-day week, regular session/crosses retained.
- [Nasdaq holiday schedule](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule): reference for source-owned calendar rows. Tests use explicitly synthetic calendars; downloading this page is not an attestation of every future session.
- [IBKR existing overnight](https://www.interactivebrokers.com/en/trading/us-overnight-trading.php): 20:00–03:50 ET and distinct holiday exceptions; SMART+OVERNIGHT is distinct from Nasdaq's new night session. No new IB/account entitlement is inferred.
- [Massive Form T](https://massive.com/knowledge-base/article/does-a-form-t-trade-update-a-pre-market-minute-bars-high-low-open-and-close): existing daily price/volume eligibility differs from minute-bar eligibility. New Nasdaq night coverage remains UNKNOWN.

Original HTTP bodies and acquisition/SHA receipts, 17-symbol reference results and volume CSVs are in the private delivery evidence. No broker instruction or order is needed or submitted.

## Actual upstream call chain and minimal changes

Before this increment, `W8/v82_approved_context.read_source()` only passed the operator file's `session` through `build()`. `W5/v82_slice_bridge.ensure_cycle()` looked up a cycle using that external session ID. No production night trade-date generator existed in this path. `daily_slice.cycle_id/open_cycle/update_intent` already preserved a supplied correct ID and B0; their source bytes are unchanged.

The new single interpreter is `W5/market_session_source.read()`. It reads pinned operator session facts, validates owner/asset/DB identity before reading referenced originals, and derives a session from source-owned venue/calendar intervals. `W8/v82_approved_context.read_source()` uses it instead of an arbitrary supplied session when `session_source` is present. An inconsistent hand-written session is rejected. `W5/v82_slice_bridge.bind()` independently replays it, checks cycle/session identity and uses the derived readiness/open state. `ensure_cycle()` resolves before the original lookup; it never recalculates B0 or writes a new ledger as part of this adapter.

After the announced Nasdaq launch instant, legacy US planning keys without the bound venue source cannot initialize a new cycle. This is a proof requirement, not automatic activation. `NASDAQ`, `XNAS`, `NYSE`/`XNYS`, `ARCA`/`ARCX`/`NYSEARCA`/`NYSE_ARCA`, `AMEX`/`XASE` are recognized planning-key aliases. The caller preserves the original planning exchange string to retain the native key; `execution_venue` is a separate field. Do not substitute a venue name for an existing planning-exchange ID.

The interpreter supports the candidate Nasdaq rule and current IB ATS night classification separately. It does not apply Nasdaq's 20:00 pause or new SIP prerequisite to IB ATS. SMART daytime and IB holiday-hours exceptions need their own route/exception proof and remain closed/UNKNOWN in this adapter. For Nasdaq 04:00 handoff, a missing explicit transition-end fact leaves pre-market transition status UNKNOWN. No interval is silently assumed uninterrupted.

Calendar `days` must cover every date of its declared range, including explicit CLOSED rows. OPEN rows include the prior calendar date's night start and their regular/day boundaries. Friday night is not rolled forward to Monday. Early-close day-end is supplied explicitly with its source reference; no afternoon/overnight timetable is invented. Time comparisons normalize aware timestamps with `America/New_York`, retaining DST and half-open boundaries.

`member_market_source.read_market()` retains provider daily-date labeling. An explicit night-quote kind and an explicitly intraday Yahoo granularity cannot enter daily calculations. After the announced cutover, missing Yahoo granularity also remains unresolved. Daily bar dates are never remapped using event trade-date logic. Massive, Nasdaq and IB daily adapters and the approved technical producer retain their original values and code.

Five existing CI workflows add only relevant candidate paths; the post-trade PR filter also adds the stack base branch. Job commands and assertions are unchanged. Direct dependency hashes and the existing C7 manifest include the new source dependency; no strategy contract or native kernel is changed.

## Source contract

The supplemental approved-source JSON accepts `session_source: {local_path, sha256}`. Do not include a pasted `session_source_readback`. The pinned file uses `Family.W5.MarketSessionSource.v1`, with:

- `owner`, `asset_id`, `source_db_sha256`, `available_at`, `source_reference`;
- `execution_venue` (`NASDAQ` or `IBKR_ATS`), the unchanged `planning_exchange` key, positive broker `contract_id` and the matching named `rules_profile`;
- `originals`: pinned SHA, acquisition time and source references;
- `calendar`: venue, timezone, ID/version, inclusive date coverage and explicit daily session rows, source hash, availability and assurance;
- `readiness`: venue/profile-bound, independent exchange-operation, data-feed, broker-route and account-permission proofs; Nasdaq also requires SIP readiness. Feed/route/account proofs bind the exact asset; route/account proofs also bind owner and contract ID.

`SOURCE_VERIFIED` is an operator/source-owner attestation bound to the referenced original and cutoff, subject to independent QA. Merely downloading an official announcement does not supply these attestations. Missing proof never becomes VERIFIED. Tests use `SYNTHETIC` assurance and explicit trusted synthetic opt-in; that opt-in cannot be selected by request data. Actual sources use the default source-only mode. Unknown or not-yet-started conditions keep `open_for_planning=false`. No fee, cash, event-release, entitlement or source qualification is inferred.

## T01–T11 evidence boundaries

| Case | Executable coverage / evidence | Remaining real gate |
| --- | --- | --- |
| T01 | Announced start and pre-start rejection; ET/Taipei mapping | Actual production start/SIP proof |
| T02 | Midnight + timezone variants, original cycle ID and B0 | Real event trade-date field |
| T03 | Adjacent boundary seconds, explicit 04:00 handoff, IB ATS distinction | Actual transition status and broker routing |
| T04 | Explicit closed days, weekends, early end, DST, missing-calendar rejection | Source-owner attested full production calendar |
| T05 | Existing durable cycle lookup, restart/replay/Target change; fixed B0 | Qualified real source/ledger authority |
| T06 | Original pending/partial/spent/committed, confirmed and local release; late fills | Actual broker event lineage/settlement |
| T07 | All 17 symbols, official directories and actual current IB contract references | Each new feed/route/account status UNKNOWN |
| T08 | QQQ/NVDA raw daily vs observed RTH minute volumes and original native M8 sensitivity | Full 17-asset/new-night eligibility; Owner approval before any basis change |
| T09 | Daily-provider dates preserved; night/intraday rejection and old indicator regression | New feed semantics/latency/actual final daily availability |
| T10 | New unit/integration plus existing W5/W8 and six CI | Source-backed live Nasdaq/SIP/IB certification |
| T11 | No exchange-session-end release or automatic resubmission; original broker confirmation | Actual broker acknowledged lifecycle |

T07 set: ADBE, AVGO, CPAI, DRAM, DYNF, GOOG, IBKR, MDT, MSFT, NVDA, PPH, QQQ, SGOV, SMH, SOXX, VT, ZTS. This is a compatibility set, not a holdings list or trading authorization. Directory membership is a current observation, not a future security-status or live-route guarantee.

T08 preserves four exact provider CSVs for 2026-10-06 through 2026-11-05. Each symbol has 23 daily observations and its full returned minute series. The comparison sums observed 09:30–16:00 ET minute volume, keeps daily prices fixed, and calls the unchanged native technical producer for the six available 20-prior-bar comparison points. These samples show no M8 component changes; they do not establish universal equivalence. Missing trade-condition/coverage and future night-feed facts remain explicit. No RTH-only input substitution or investment-rule change is adopted.

This is engineering compatibility evidence. It is not a performance backtest, actual exchange certification, user/device E2E, financial PASS, account qualification or production release. PM owns independent acceptance and governance; existing PR59 remains Draft/unmerged.
