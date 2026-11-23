"""Save one original menu 03 event into a candidate workbook using openpyxl."""
import json
import os
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

ROLES = ('主軸', '衛星', '繁星')
NAMES = ('方案一', '方案二', '方案三')
STEPS = dict(home='選擇工作方案', goal='投資目標', returns='偏好年報酬', loss='可接受跌幅',
             band='選配置範圍', exact='確認層級比重', theme='選產業方向', symbol='選標的',
             weight_band='選標的比重範圍', weight='選標的比例', fund='資金來源', amount='金額範圍',
             replace='選擇擬換出的持股', review='檢視完整方案', compare='六組比較',
             reduce='選減碼標的', increase='選加碼標的', shift='選移動比重')


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def put(sheet, row, col, values):
    for j, value in enumerate(values, col):
        cell = sheet.cell(row, j)
        cell.value = value
        if isinstance(value, str):
            if len(value) > 32767:
                raise ValueError('選擇紀錄超過 Excel 儲存格容量')
            cell.data_type = 's'


def header(sheet, row, values):
    put(sheet, row, 1, values)
    for cell in sheet[row][:len(values)]:
        cell.fill = PatternFill('solid', fgColor='175950')
        cell.font = Font(color='FFFFFF', bold=True)
    sheet.row_dimensions[row].height = 25


def table(book, name, titles, widths):
    sheet = book[name] if name in book else book.create_sheet(name)
    header(sheet, 1, titles)
    for j, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(j)].width = width / 7
    sheet.freeze_panes = 'A2'
    return sheet


def weights(layer):
    return '、'.join(f'{symbol} {pct}%' for symbol, pct in layer.items())


def comparison(book, event):
    advice = event['advice']
    if '六組比較' in advice:
        sheet = table(book, '六組比較',
            '時間 方案 股票配置 資料起日 資料迄日 幣別 狀態 期間報酬 年化報酬 最大回撤 年化波動 Sharpe Sortino Calmar 特點與取捨 共同成分或產業（已知百分點） 相對全VT的優點 相對全VT的代價'.split(),
            [180,88,280,120,120,70,180,105,105,105,105,90,90,90,360,400,330,330])
        put(sheet, 1, 17, ['相對全 VT 的優點', '相對全 VT 的代價'])
        for r in advice['六組比較']:
            h = r['歷史試算']
            overlap = '、'.join(f"{x['項目']} {x['已知合計百分點']}" for x in r['共同曝險']['共同曝險'])
            row = sheet.max_row + 1
            put(sheet, row, 1, [event['time'], r['名稱'], weights(r['股票桶百分比']),
                *(h.get(k) for k in ('起日','迄日','幣別','狀態','期間報酬率','年化報酬率','最大回撤幅度','年化波動率','Sharpe','Sortino','Calmar')),
                '；'.join([r['取捨'], *r.get('六組相對特點', [])]), overlap or '已知資料未列出重疊',
                '、'.join(r['相對優點']), '、'.join(r['相對代價'])])
            for col in range(8, 15):
                sheet.cell(row, col).number_format = '0.00%' if col <= 11 else '0.00'
    if advice.get('本人偏好對照'):
        sheet = table(book, '本人偏好對照', '選擇時間 偏好來自 本人目標 年報區間 跌幅偏好 比較對象 歷史年報對照 歷史跌幅對照 家人版建議'.split(),
                      [195,105,220,165,165,110,145,190,540])
        for pref in advice['本人偏好對照']:
            for r in pref['六組對照']:
                put(sheet, sheet.max_row + 1, 1, [event['time'], *(pref[k] for k in ('偏好來自','目標','年報區間','跌幅偏好')),
                    *(r[k] for k in ('名稱','報酬對照','回撤對照')), pref['家人版建議']])
    if '六組比較' in advice:
        return {'六組比較': [dict(r, 共同曝險={'共幾項':len(r['共同曝險']['共同曝險']), '明細':'見六組比較頁'}) for r in advice['六組比較']]}
    return advice


def update_plans(book, main, alloc, event):
    state = event['answers']
    plans, slot = state['plans'], state['slot']
    for row in main['A6:F20']:
        for cell in row:
            cell.value = None
            cell.style = 'Normal'
    header(main, 6, ['工作方案', *ROLES])
    for i, p in enumerate(plans):
        put(main, 7+i, 1, [NAMES[i], *(weights(p['layers'][r]) or '尚未選擇' for r in ROLES)])
    put(main, 11, 1, ['目前方案', NAMES[slot]])
    put(main, 12, 1, ['最後指定', (state.get('final') or {}).get('方案', '尚未指定')])
    put(main, 14, 1, ['本案偏好', '／'.join(plans[slot]['prefs'].values())])
    alloc.delete_rows(1, alloc.max_row)
    header(alloc, 1, ['方案','角色','標的','占股票部位','版本狀態'])
    for i, p in enumerate(plans):
        for role in ROLES:
            for symbol, pct in p['layers'][role].items():
                row = alloc.max_row + 1
                put(alloc, row, 1, [NAMES[i], role, symbol, pct/100, '目前工作稿'])
                alloc.cell(row, 4).number_format = '0%'
    if event['key'] in ('save', 'final'):
        hist = table(book, '方案版本', '日期與時間 當時方案 主軸 衛星 繁星 當時決定 版本識別'.split(), [195,100,280,280,280,180,290])
        put(hist, hist.max_row + 1, 1, [event['time'], NAMES[slot], *(weights(plans[slot]['layers'][r]) or '0%' for r in ROLES), event['stage'], event['id']])


def save(args):
    src, dest = Path(args['input']), Path(args['output'])
    if src.resolve() == dest.resolve():
        raise ValueError('需使用獨立候選檔')
    event, member = args['event'], args['member']
    book = load_workbook(src)
    main, alloc, log = (book[n] for n in ('選擇進度','標的及比例','選擇歷程'))
    if main['B1'].value != member or log.max_row != event['previous'] + 1:
        raise ValueError('家人身分或選擇進度已變動')
    advice = comparison(book, event)
    put(log, log.max_row + 1, 1, [event['id'],event['time'],member,event['key'],event['title'],compact(event['options']),compact(advice),event['choice'],event['url'],event['stage'],compact(event['answers']),event.get('token') or ''])
    put(main, 2, 2, [event['stage']])
    put(main, 3, 2, [STEPS.get(event['next'], event['next'])])
    if event['answers'].get('schema') == 2:
        update_plans(book, main, alloc, event)
    else:
        answers = event['answers']
        questions = json.loads(Path(__file__).with_name('family03_questions.json').read_text())
        for row, key in enumerate(questions, 7):
            put(main, row, 3, [answers.get(key)])
        put(alloc, 2, 2, [event['stage']])
        for i,key in enumerate(('core','sat','star')):
            pct = event['mix'][i]/100 if event.get('mix') is not None else None
            picked = answers.get(key)
            put(alloc, i+5, 2, [picked, pct if picked else None, pct, event['stage'] if picked else None])
    with tempfile.NamedTemporaryFile(dir=dest.parent, suffix='.xlsx', delete=False) as tmp:
        candidate = Path(tmp.name)
    try:
        book.save(candidate)
        os.replace(candidate, dest)
    finally:
        candidate.unlink(missing_ok=True)
        book.close()


if __name__ == '__main__':
    save(json.loads(Path(sys.argv[1]).read_text()))
