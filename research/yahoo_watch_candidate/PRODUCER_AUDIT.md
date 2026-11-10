# Original producer integration audit, 2026-11-10

## New real-data result, not a full V82 claim
The original PR59 commit `3f7ea0dcd2963ae55598ffa90b36893ed47cc9bb` was freshly checked out without tracked edits. Its original qualified-equity test suite passed 25/25. Fresh read-only IBKR VT identity and FIVE_YEARS/ONE_DAY/outside_rth=false sources returned 1,252 bars and 20 cash dividend actions. Fresh Yahoo FIVE_YEARS daily source supplied 1,254 bars through 2026-11-09. These are separate sources, not a claim of equal row counts or historical PIT coverage.

The original `qualified_equity_inputs.item` accepted the captured, hash-bound Yahoo/IBKR/calendar evidence as FRESH. The original `approved_v04_technical.produce` and original technical aggregation returned:
- right_confirmation = TRUE
- runaway_up = FALSE
- runaway_down = FALSE

This does NOT establish full Right Entry, Stage, safety, buy permission, cash or quantities. No account state was fetched, and no trading occurred. The qualification artifact hash for this local replay is `ca6c3253e3545823d21d29c1b043a65212ff81a12fd69b7e54d4f3459d34069a`. Raw provider data and local paths are not published in this candidate.

## Exact remaining implementation gaps
In the unchanged original `Family/W8/formal_mode_analysis.py`, build_formal_conclusion currently constructs:
```
price_conditions = {
  'valuation_reasonable_or_cheap': value_zone,
  'price_map_zone': None,
  'near_confirmed_low': None,
  'near_important_ma_or_support': None,
  'meaningful_drawdown': None
}
```
Thus only a legal NORMAL/CHEAP valuation can currently make this OR true; the other four routes are not wired at this boundary. Additional Yahoo intraday quotes cannot turn these hard-coded absent inputs into verified facts. Replacing None with TRUE, a hand-picked percentage or a new proxy would be an unauthorized strategy change.

The same original function sets `uncontrollable_event_gap_clear=None`, and event_coverage explicitly says existing news rows are not a verified negative search/complete event registry. Viability and credit also retain their existing source contracts. These are independent of successful technical calculation.

The current source qualification adapter explicitly supports VT and QQQ only. Expanding instruments needs identity/calendar/company-action validation; do not silently generalize US ETF assumptions to Taiwan, ADRs or futures. The original scoped adapter requires IB source captures which are accessible in the interactive research session, but GitHub does not inherit that connector authentication. A fresh scheduled source capture/transfer path is still required.

## Reusable replay entry point
`replay_original_technical.py` runs the original qualified source and approved technical implementation from the pinned clean checkout. It requires a local qualification artifact and expected SHA; it never constructs permissive source receipts, rewrites formulas or changes original files. It emits only technical-level results with L_price/Buy Permission UNKNOWN and trade_action NONE. Current-state source qualification does not grant historical publication-time PIT.

The draft can end-to-end test source -> original technical signals -> isolated monitor projection. It cannot honestly end-to-end validate complete L_price -> safe buy recommendation until the four original price routes and independent safety evidence are wired by the responsible runtime owner. No further mailbox infrastructure is needed to explain this boundary.
