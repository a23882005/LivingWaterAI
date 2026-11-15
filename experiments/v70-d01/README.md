V70 D01 isolated SAHMREALTIME reader

This candidate branch runs only the standalone D01 reader against the existing
FRED_API_KEY GitHub Actions binding. It does not modify production source selection,
crawlers, feeds, last-valid state, workflows on main, schedules, or deployment.

The reader requests the exact SAHMREALTIME series and the 2026-11-15 real-time
cutoff. A successful technical read does not approve public reuse, derived uses,
or admission into the 26-variable source registry. Source notes and usage evidence
remain separate qualification work.

Tests use the previously observed missing-key response and clearly marked synthetic
identity/security fixtures. No source values or raw metadata are printed in CI.
Raw results are encrypted with the public recipient certificate before upload.
The private decryption key is held only in the local engineering workspace; it
is not committed, uploaded, or used as an API/account credential.

The workflow has read-only repository permission, no manual/scheduled/main trigger,
no full collector invocation, and no publication or notification step.
