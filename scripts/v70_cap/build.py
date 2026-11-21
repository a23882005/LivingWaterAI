"""Render only the protected engineering output after the standard site build."""
import argparse
import json
import re
from pathlib import Path

from rules import FIELDS, RULES, TESTS, evaluate

PANEL = '''<section id="engineering-cap" hidden aria-live="polite" style="margin-top:1rem;padding:1rem;border-radius:.75rem;color:white;line-height:1.65">
<strong style="font-size:1.35rem"></strong><div style="white-space:pre-line"></div><p></p>
<small>歷史比較｜2002年11月至2026年11月，原合併警報共42回，其中41回有亮燈後30天資料。此統計包含單獨 VIX 警報。30天是比較期間，暫停期間依本期燈號決定。</small></section>'''

def once(html, old, new):
    if html.count(old) != 1:
        raise ValueError('Engineering template mismatch: '+old[:64])
    return html.replace(old,new,1)

def build(source, destination):
    html=(source/'index.html').read_text()
    feed=json.loads((source/'V70_macro_latest.json').read_text())
    values={key:feed['indicators'].get(key,{}).get('value') for key in FIELDS}
    values['m21'] = feed.get('derived', {}).get('m21', {}).get('value')
    if isinstance(values['m02'],(int,float)) and values['m02']>=50:
        values['m02']/=100
    feed['engineeringCap']={**evaluate(values),'asOf':feed['asOf'],'inputs':values,
                            'dates':{k:feed['indicators'].get(k,{}).get('dataDate') for k in FIELDS}}
    data=json.dumps(feed,ensure_ascii=False,indent=2,allow_nan=False)
    pattern=r'(<script id="v70-embedded-feed" type="application/json">).*?(</script>)'
    html,count=re.subn(pattern,lambda m:m[1]+data.replace('<','\\u003c')+m[2],html,flags=re.S)
    if count!=1: raise ValueError('Missing embedded engineering feed')
    def condition(token):
        key = token.lstrip('!')
        if key == 'B':
            return '（' + condition('inflation') + ' 且 ' + condition('rise') + '）'
        field, op, threshold = TESTS[key]
        sign = ('<' if op == 'ge' else '>') if token.startswith('!') else ('≥' if op == 'ge' else '≤')
        return f'{FIELDS[field]} {sign} {threshold}'

    catalog = []
    for row in RULES:
        parts = [condition(k) for k in row['match'] if row['layer'] != '危機' or not k.startswith('!')]
        suffix = '（其餘危機條件未達標）' if row['layer'] == '危機' and len(parts) < 5 else ''
        catalog.append(f"<li>{row['id']}｜{row['layer']}層 CAP {row['cap']}｜" + ' 且 '.join(parts) + suffix + '</li>')
    catalog = '<details><summary>查看全部 34 項封頂條件</summary><ul>' + ''.join(catalog) + '</ul></details>'
    js=Path(__file__).with_name('panel.js').read_text().replace('__V70_CAP_RULES__',
        json.dumps(dict(fields=FIELDS,tests=TESTS,rules=RULES),ensure_ascii=False))
    html=once(html,'</head>','<script>'+js+'</script></head>')
    start=html.index('<div class="hidden absolute inset-0',html.index('id="macro-zone-text"'))
    end=html.index('</div>\n</div>\n</div>',start)+len('</div>\n</div>')
    assert 'circuit-breaker-overlay' in html[start:end]
    html=html[:start]+PANEL+catalog+html[end:]
    for anchor,element in [('<div class="space-y-4" id="allocation-list">','cap-allocation-note'),
                           ('<div aria-live="polite" class="rounded-lg bg-slate-800 p-4 text-sm space-y-3" id="v703-result">','cap-family-note')]:
        html=once(html,anchor,'<p id="'+element+'" class="font-bold mb-2"></p>'+anchor)
    start=html.index('            // 恐慌層\n',html.index('function calcTotal()'))
    end=html.index('            const capMin',start)
    html=html[:start]+'''            const caps = window.v70Cap.render(getRaw);
            const cap_panic = caps.layers['恐慌'], cap_crisis = caps.layers['危機'], cap_recession = caps.layers['衰退'];
            const panicWhy = caps.reasons['恐慌'].join('；'), crisis = caps.crisisPoints, recWhy = caps.reasons['衰退'];
            const sahm=getRaw('m18'), lei_yoy=getRaw('m16'), u3=getRaw('m19'), nfp_3m_avg=getRaw('m20');
            const lei_neg_3m=getRaw('m21')>=1;
'''+html[end:]
    start=html.index('            // 是否進入',html.index("const zEl = document.getElementById('macro-zone-text')"))
    end=html.index('            // Allocation / Orders',start)
    html=html[:start]+'''            const isEmerg = caps.level==='red';
            zEl.textContent=Number.isFinite(mSafe_final)?(mSafe_final>=70?'體質良好':mSafe_final>=55?'體質尚穩':mSafe_final>=40?'體質偏弱':'體質不佳'):'資料不足';
'''+html[end:]
    html=once(html,'provisional ? NaN : computedFinal','provisional || caps.missing.length ? NaN : computedFinal')
    html=once(html,'if(provisional&&Number.isFinite(computedFinal))','if(provisional&&!caps.missing.length&&Number.isFinite(computedFinal))')
    html=once(html,"box.innerHTML='<div class=\"text-amber-200 font-bold\">⚠ 正式八類配置", "box.innerHTML=(snap?.isEmerg?'系統熔斷中，暫停買賣。':'')+'<div class=\"text-amber-200 font-bold\">⚠ 正式八類配置")
    html=once(html,'fiveClassMacroAdvice:fiveAdvice','fiveClassMacroAdvice:snap.isEmerg?fiveAdvice?.map(x=>({...x,advice:"暫停買賣"})):fiveAdvice')
    html=once(html,'恐慌CAP60已觸發：審查信用／流動性，不強制清倉','系統熔斷中，暫停買賣與調倉')
    for var in ('sa','ba'):
        html,n=re.subn(r'if\(isEmerg\) \{ '+var+r'=`[^`]*`; [sb]c="text-red-500 animate-pulse"; \}',
                  'if(isEmerg) { '+var+'="系統熔斷中，暫停買賣。"; '+var[0]+'c="text-red-400"; }',html)
        if n!=1: raise ValueError('Missing order '+var)
    html=once(html,'${x.advice}',"${snap.isEmerg?'暫停買賣':x.advice}")
    html=once(html,'${labels[x[0]]}：${x[1]}',"${labels[x[0]]}：${snap.isEmerg?'暫停買賣':x[1]}")
    html=once(html,"[k,(window.v703DemoMode?", "[k,snap.isEmerg?'暫停買賣':(window.v703DemoMode?")
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'index.html').write_text(html)
    (destination/'V70_macro_latest.json').write_text(data+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    build(args.source,args.destination)
