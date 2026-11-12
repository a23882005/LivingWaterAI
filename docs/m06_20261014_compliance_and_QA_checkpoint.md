# V70.3 m06 checkpoint — 2026-10-14

## Verified evidence
- GitHub Actions run 38519144067 / job 115704591680 returned `CANDIDATE_NEEDS_REVIEW`, settlement date 2026-10-13, meeting 2027-10-27, +3.2783 quarter-points of 0.25% each (rate increase quarters).
- Run succeeded and artifact `m06-free-probe` ID 11873211056 exists. Green workflow status alone does not establish a validated observation.
- A distinct CME website NOW screenshot, as described by handoff, produced approximately +3.2192 quarter-point changes; **different timestamps** prevent same-settlement-date cross-verification.
- Main production audit remains 17/23. PR #5 stays draft and not merged.

## New tests / CI
- tests/test_m06_fedwatch_free.py covers +/− expected changes, weekend/holiday settlement age, future/stale dates, probability sums, invalid target rate width, 12-month meeting-window selection, non-FRED current target.
- Independent m06 probe workflow runs this regression suite before the network probe.
- These are offline contract tests; live multi-day and same-date official parity remain incomplete.

## Compliance gate: HOLD production
Official terms (read 2026-10-14):
- https://www.cmegroup.com/trading/market-data-explanation-disclaimer.html
- https://www.cmegroup.com/tools-information/cme-website-terms-of-use.html
- https://www.cmegroup.com/articles/faqs/access-to-cme-group-settlement-data-faq.html

CME publicly states that website data uses are restricted, website automated collection and software/data mining require authorization, and its free website settlement display is distinct from a licensed data feed. Open-source package availability and personal CME registration do not grant an API/data redistribution license. Do not schedule further unattended live harvesting, merge free extractor to production, redistribute CME data, or promote a candidate to OK until access method and intended automated/website uses are expressly authorized or replaced with a separately licensed source.

## Remaining DoD
1. Confirm rights for unattended daily retrieval, computation, storage, and any end-user report/display (document license or approved vendor).
2. Compare the SAME settlement date and meeting's full probability distribution to authorized official data; record differences and tolerances.
3. Obtain at least 3 distinct trading-day observations from authorized channel, with holiday, missing data, stale and roll-boundary handling.
4. Record full provenance (settlement date/time zone, retrieval date, meeting date, rate target as-of, source/method).
5. Reconcile against current latest main before an approved backup/merge; current official m06 remains MISSING.

Do not expose any FRED/CME token in repository artifacts or logs.
