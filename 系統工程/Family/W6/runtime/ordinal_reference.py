"""W6 rule-based ordinal reference, not a return or drawdown forecast."""
from math import floor, isfinite

def portfolio_grade(holdings, matrix, scenario, direction):
    if direction not in ('attack', 'defense'):
        raise ValueError('unknown direction')
    if scenario not in matrix['scenario_order']:
        raise ValueError('unknown scenario')
    lookup = {r['id']: r for r in matrix['rows']}
    seen = set()
    total_weight = known_weight = weighted = 0.0
    detail = []
    for h in holdings:
        key = h['asset_id']
        if key in seen:
            raise ValueError('duplicate asset')
        seen.add(key)
        w = h['weight']
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not isfinite(w) or w < 0:
            raise ValueError('invalid weight')
        total_weight += w
        code, tenor = h.get('class_id'), h.get('tenor', 'none')
        if tenor not in ('none', 'short', 'medium', 'long'):
            raise ValueError('invalid tenor')
        if code == 'CASH':
            value = 1 if direction == 'attack' else 6
        elif code in lookup:
            value = lookup[code]['scenarios'][scenario][direction]
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 6:
                raise ValueError('invalid baseline grade')
            if code in ('B05', 'B06'):
                if tenor == 'short':
                    if direction == 'defense':
                        value += 1
                    elif scenario in ('牛市初期', '景氣衰退', '金融危機'):
                        value -= 1
                    if code == 'B06' and direction == 'defense' and scenario in ('景氣衰退', '金融危機'):
                        value = min(2, value)
                elif tenor == 'long':
                    if direction == 'defense':
                        value -= 1
                    elif code == 'B05' and scenario == '景氣衰退':
                        value += 1
            value = min(6, max(1, value))
        else:
            detail.append({'asset_id': key, 'weight': w, 'grade': None})
            continue
        known_weight += w
        weighted += w * value
        detail.append({'asset_id': key, 'weight': w, 'grade': value})
    if abs(total_weight - 1) > 1e-9:
        raise ValueError('weights must sum to one')
    complete = abs(known_weight - total_weight) <= 1e-9
    grade = min(6, max(1, floor(weighted + .5))) if complete else None
    return {'coverage': known_weight, 'known_contribution': weighted,
            'raw': weighted if complete else None, 'level': grade,
            'grid': grade / 2 if grade is not None else None, 'detail': detail,
            'method': matrix['version']}
