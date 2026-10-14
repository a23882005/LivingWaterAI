# Family PF｜Private OAuth Issuer Rejection Checkpoint
Date: 2026-10-13, Asia/Taipei

## Actual changes
- `pf_remote_preflight.py`: resource metadata discovery now rejects OAuth issuer addresses pointing to localhost, non-global IPs, and reserved placeholder domains.
- `test_remote_preflight.py`: five negative test cases cover localhost, loopback IPv4, link-local IPv4, private IPv6, and test-domain issuer.
- Code commits: `640c22923891bd682a89f78705be65411851f934` and `9e1eb37fdb1eb7b0a669a5ff465fc21eaad4ef46`.
- [GitHub Actions #38418364164](https://github.com/a23882005/LivingWaterAI/actions/runs/38418364164): completed SUCCESS; pytest **201 passed, 1 warning in 10.63s**; demo SUCCESS.

## Unverified external acceptance
- URL checks are preliminary and do not establish DNS rebinding resistance, issuer authenticity or a real OAuth login.
- No verified external HTTPS MCP, externally provisioned IdP, remote tenant-isolation E2E, independent immutable audit log storage/anchor or independent reviewer sign-off.
- Gate A HOLD; WORK13 0/29; Draft PR #2. No main merge, production runtime edits, real client data or new paid hosting.
