"""Positive arithmetic replay on real captured history plus original W5 rejection.

Independent Decimal reference checks cover moving averages, volume ratios, and
TD9 counts. This is not a positive full-strategy/FamilyRunner decision fixture.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from capture_receipt import read_capture
from replay import differences, digest, verify_files


def numeric_reference(rows):
    close = [Decimal(r['Close']) for r in rows]
    volume = [Decimal(r['Volume']) for r in rows]
    expected = {}
    for n in (5, 10, 20, 50, 60, 200):
        expected['ma' + str(n)] = round(float(sum(close[-n:]) / n), 6)
    for n in (5, 20, 50):
        expected['volume_ratio_' + str(n)] = round(float(volume[-1] / (sum(volume[-n:]) / n)), 6)
    signs = [(a > b) - (a < b) for a, b in zip(close[4:], close[:-4])]
    side, count = signs[-1], 0
    for sign in reversed(signs):
        if not side or sign != side or count == 9:
            break
        count += 1
    expected.update(high_td9_setup=count if side > 0 else 0, low_td9_setup=count if side < 0 else 0)
    return expected


def run(handoff, output):
    home = Path(__file__).resolve().parent
    handoff, output = Path(handoff).resolve(), Path(output).resolve()
    source = home / 'evidence/capture_proof'
    pin = json.loads((home / 'capture_release.json').read_text())['receipt_sha256']
    cutoff = '2026-10-20T12:00:00Z'
    selected = read_capture(source / 'source_capture.zip', source / 'receipt.json',
                            trusted_receipt_sha256=pin, cutoff=cutoff)
    lock = json.loads((home / 'source_lock.json').read_text())
    verify_files(handoff, lock)
    w5 = handoff / 'repo/系統工程/Family/W5'
    root = handoff / 'baseline/sources'
    sys.path[:0] = [str(w5), str(w5 / 'tests')]
    os.environ['W5_SOURCE_ROOT'] = str(root)
    import pandas as pd
    from technical_source_bridge import _originals
    _, original = _originals()
    rows = [r for r in selected['rows'] if r['Date'].startswith('2026-')]
    expected = numeric_reference(rows)
    first = original.technical(pd.DataFrame(rows))
    second = original.technical(pd.DataFrame(rows))
    assert len(rows) == 200 and not differences(first, second)
    actual = {key: first[key] for key in expected}
    assert not differences(expected, actual), differences(expected, actual)
    # Replay the saved W5 real-market/synthetic-caller safety fixture. Relocate
    # only its local path and recompute path-bound request metadata explicitly.
    from family_runner import FamilyRunner
    from test_stock_source_bridge import refresh
    from family_input import digest as w5digest
    intake = handoff / 'market_intake'
    request = json.loads((intake / 'VOO.family_request.json').read_text())
    context = json.loads((intake / 'VOO.family_context.json').read_text())
    old_path = context['technical_source']['csv_path']
    context['technical_source']['csv_path'] = str(intake / 'VOO.csv')
    request['technical_source_digest'] = w5digest(context['technical_source'])
    refresh(request, context)
    golden = json.loads((intake / 'VOO.family_result.json').read_text())
    results = [FamilyRunner(root, context_provider=lambda: deepcopy(context)).analyze(deepcopy(request)) for _ in range(2)]
    assert not differences(golden, results[0]), differences(golden, results[0])[:3]
    assert not differences(results[0], results[1])
    assert results[0]['status'] == 'DATA_UNAVAILABLE' and results[0]['trade_action'] == 'NO_TRADE'
    verify_files(handoff, lock)
    result = {'status': 'PASS', 'cutoff': cutoff,
              'capture': {k: v for k, v in selected.items() if k != 'rows'},
              'positive_numeric_replay': {'status': 'PASS', 'rows': len(rows), 'independently_checked_fields': len(expected),
                                          'expected': expected, 'actual': actual, 'executions': 2},
              'original_w5_safety_replay': {'status': 'PASS', 'result_status': results[0]['status'],
                  'golden_exact_match': True, 'executions': 2, 'original_path': old_path,
                  'relocation': 'CSV path only, technical digest and native binding refreshed',
                  'provenance': 'REAL_MARKET_WITH_SYNTHETIC_CALLER_SAFETY_ONLY'},
              'full_historical_strategy_positive': False, 'trade_authorization': 'NONE'}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    run(*sys.argv[1:])
