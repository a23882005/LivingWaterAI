"""V70 engineering alerts. The browser evaluates this same rule table for manual input."""
import math

# An interval includes its lower bound and excludes its upper bound.
# Thresholds that include an upper bound use le.
FIELDS = {
    'm07': 'VIX', 'm12': 'MOVE', 'm02': '高收益債信用利差（%）',
    'm13': '五年通膨預期（%）', 'm17': '近一月變化（百分點）',
    'm14': '13週淨流動性變化（十億美元）', 'm08': '十年實質利率（%）',
    'm18': '薩姆指標', 'm16': 'LEI年增率（%）', 'm19': '失業率（%）',
    'm20': '非農就業三月平均增量', 'm21': 'LEI年增率連三月為負（1＝是）',
}
TESTS = {
    'v28': ['m07','ge',28], 'v35': ['m07','ge',35], 'move140': ['m12','ge',140],
    'A': ['m02','ge',6], 'inflation': ['m13','ge',2.6], 'rise': ['m17','ge',0.25],
    'C': ['m12','ge',160], 'D': ['m14','le',-500], 'E': ['m08','ge',2.5],
    's04': ['m18','ge',0.4], 's05': ['m18','ge',0.5], 'jobs': ['m20','le',0],
    'lei3': ['m21','ge',1], 'lei4': ['m16','le',-4], 'u45': ['m19','ge',4.5],
}
COMBOS = {4:'AC',5:'BC',6:'CD',7:'CE',8:'ABC',9:'BCD',10:'BCE',11:'ACD',
          12:'ACE',13:'CDE',14:'ABCD',15:'ABCE',16:'ACDE',17:'BCDE',18:'AB',
          19:'BD',20:'BE',22:'AD',23:'AE',24:'DE',25:'ABD',26:'ABE',27:'ADE',
          28:'ABDE',29:'ABCDE',31:'BDE'}
def rule(number, layer, cap, match):
    return dict(id=f'{number:02}', layer=layer, cap=cap, match=match)

RULES = [rule(1,'恐慌',60,['v28','move140']), rule(2,'恐慌',70,['v28','!v35','!move140']),
         rule(3,'恐慌',60,['v35','!move140'])]
for number, combo in COMBOS.items():
    RULES.append(rule(number,'危機',55 if len(combo)==2 else 45,
                      [c if c in combo else '!'+c for c in 'ABCDE']))
RULES += [rule(21,'衰退',55,['s04']), rule(30,'衰退',45,['jobs']),
          rule(32,'衰退',45,['s05']), rule(33,'衰退',55,['lei3','u45']),
          rule(34,'衰退',45,['lei4','u45'])]
RULES.sort(key=lambda r:r['id'])

def evaluate(values):
    flags = {}
    for key,(field,op,threshold) in TESTS.items():
        value = values.get(field)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            flags[key] = None
        else:
            flags[key] = value >= threshold if op=='ge' else value <= threshold
    flags['B'] = (False if False in (flags['inflation'],flags['rise']) else
                  None if None in (flags['inflation'],flags['rise']) else True)
    matched = [r for r in RULES if all(flags[token.lstrip('!')] is (not token.startswith('!'))
                                        for token in r['match'])]
    if any(r['layer']=='衰退' and r['cap']==45 for r in matched):
        matched = [r for r in matched if (r['layer'],r['cap'])!=('衰退',55)]
    return summarize(matched,values)

def summarize(matched,values):
    missing = [k for k in FIELDS if type(values.get(k)) not in (int,float) or not math.isfinite(values[k])]
    ids = [r['id'] for r in matched]
    cap = min((r['cap'] for r in matched),default=100)
    level = 'red' if '01' in ids else 'unknown' if missing else 'orange' if cap<=55 else 'yellow' if matched else 'normal'
    return dict(ids=ids,cap=cap,level=level,missing=missing)
