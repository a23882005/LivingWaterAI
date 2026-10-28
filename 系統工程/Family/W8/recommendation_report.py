"""Readable menu-04 output from existing results; no financial computation."""
from copy import deepcopy
from decimal import Decimal
from html import escape
from family_input import digest

GAPS={'approved_project_target_amount':'本人核准目標金額未綁定',
    'native_mode_and_stage_target_rate':'原生模式／部署階段未定',
    'verified_quote_currency':'報價幣別未核實',
    'confirmed_position_quantity_and_valuation_price':'持股估值必要欄位不足',
    'target_to_position_currency_FX':'換匯來源未接齊',
    'active_orders_and_fill_reconciliation':'本人既有未成交委託待確認'}

def money(value,currency):
    return '未定' if value is None else f'{currency or "幣別未定"} {Decimal(str(value)):,.2f}'

def percent(value):
    return '未定' if value is None else f'{Decimal(str(value))*100:g}%'

def approved_target_display(symbol,targets):
    """Merge only the two explicit SGOV roles in this approved allocation.

    This is a client display total, not a physical-role allocation or a new
    deployment target. Missing/duplicate roles and mixed money remain unknown.
    """
    matched=[x for x in targets if x.get('ticker')==symbol]
    result={'status':'UNRESOLVED','weight':None,'amount':None,'currency':None,'roles':[],'display_only':True}
    if len(matched)==1:
        row=matched[0];w=row.get('weight',{});m=row.get('target_amount',{})
        result.update(weight=w.get('value') if w.get('value_state')=='KNOWN' else None,
            amount=m.get('amount') if m.get('value_state')=='KNOWN' else None,
            currency=m.get('currency'),roles=deepcopy(matched),status='SINGLE_SOURCE_TARGET')
    elif symbol=='SGOV' and len(matched)==2 and {x.get('instrument_id') for x in matched}=={'SGOV_BOND','SGOV_DRY'}:
        if (all(x.get('weight',{}).get('value_state')=='KNOWN' and x.get('target_amount',{}).get('value_state')=='KNOWN' for x in matched)
            and len({x['target_amount']['currency'] for x in matched})==1
            and matched[0].get('source_reference_ids')==matched[1].get('source_reference_ids')):
            result.update(status='APPROVED_ROLE_TOTAL_DISPLAY_ONLY',
                weight=str(sum((Decimal(str(x['weight']['value'])) for x in matched),Decimal(0))),
                amount=str(sum((Decimal(str(x['target_amount']['amount'])) for x in matched),Decimal(0))),
                currency=matched[0]['target_amount']['currency'],roles=deepcopy(matched))
    return result


def build(report,request):
    positions=report['analysis_result']['positions'];mentor={r['item_id']:r for r in report['mentor']['items']}
    targets=request.get('confirmed_target',{}).get('payload',{}).get('draft',{}).get('target_lines',[])
    rows=[];seen=set()
    for p in positions:
        key=p['instrument_id']
        if key in seen or key not in mentor:raise ValueError('RECOMMENDATION_REPORT_COVERAGE_MISMATCH')
        seen.add(key);c=p['current_analysis'];r=c['recommendation'];j=c['current_judgment'];t=c['technical']['native_result']
        matched=[x for x in targets if x.get('ticker')==p['symbol']]
        target_view=approved_target_display(p['symbol'],targets)
        allocation=target_view['weight']
        component=r.get('confirmed_holdings_component');gap=component.get('positive_gap_amount') if component else None
        current={'Right Confirmation':'右側確認','Base Deployment':'基礎部署','Left Overweight':'左側加碼','Trend Deployment':'趨勢部署'}.get(j['mode'],j['mode']) if j['mode']!='UNKNOWN' else '模式未定'
        reasons=[]
        if c['valuation']['native_result']:reasons.append('估值 '+c['valuation']['native_result'].get('level','UNKNOWN'))
        if t:reasons.append('技術 Right '+t.get('right_confirmation','UNKNOWN')+'；Up/Down '+t.get('runaway_up','UNKNOWN')+'/'+t.get('runaway_down','UNKNOWN'))
        bond=c.get('native_component_observations',{})
        for predicate in bond.values():
            native=predicate.get('original_result',{})
            if native.get('assessment_status')=='VALID' and native.get('aggregate_state'):reasons.append(native['aggregate_state'])
        limitations=[GAPS.get(f,f) for f in r['missing_fields'] if f!='active_orders_and_fill_reconciliation']
        if target_view['status']=='APPROVED_ROLE_TOTAL_DISPLAY_ONLY':
            limitations=[f for f in limitations if f!=GAPS['approved_project_target_amount']]
            reasons.append('核准合併目標 '+percent(target_view['weight'])+'，'+money(target_view['amount'],target_view['currency'])+'；角色持倉分帳／部署階段仍待原生結果')
        if limitations:reasons.append('；'.join(limitations))
        if not reasons:reasons.append('已保留來源觀測；尚無可用的原生策略判斷')
        new_amount=r.get('new_external_funding_buy_amount')
        rows.append({'instrument_id':key,'symbol':p['symbol'],'quantity':p['holding']['quantity'],
            'market_date':c['market'].get('observed_date'),'current_judgment':current,
            'approved_allocation_weight':allocation,'approved_target_display':target_view,'stage_cumulative_rate':j.get('target_rate_reference'),
            'cumulative_target_amount':j.get('target_amount_reference'),'target_currency':j.get('currency'),
            'holding_gap_amount':gap,'holding_gap_currency':r.get('position_currency'),
            'holding_gap_label':'依已確認持股計算，尚未扣除本人既有未成交委託',
            'proposed_new_external_buy_amount':new_amount,'new_external_currency':p['owner']['currency'],
            'proposed_existing_asset_redeployment_amount':r.get('buy_gap_amount'),
            'sell_recommendation':deepcopy(mentor[key]['recommendation']['recommended_sell_amount']),
            'net_after_orders_status':'PENDING_ORDER_CONFIRMATION' if 'active_orders_and_fill_reconciliation' in r['missing_fields'] else 'SEE_NATIVE_RESULT',
            'reason':'；'.join(reasons),'remaining_analysis_fields':limitations,
            'mentor_explanation':mentor[key]['explanation']})
    if len(seen)!=len(mentor):raise ValueError('RECOMMENDATION_REPORT_MENTOR_COVERAGE_MISMATCH')
    headings=['標的／持股','目前判斷','核准配置比／階段累積比','已確認持股缺口¹','本次既有資產建議投入額','本輪新增外部資金買入²','賣出建議金額','簡短理由']
    cells=[]
    for r in rows:
        cells.append([f"{r['symbol']}／{r['quantity']}",r['current_judgment'],
            percent(r['approved_allocation_weight'])+'／'+percent(r['stage_cumulative_rate']),
            money(r['holding_gap_amount'],r['holding_gap_currency']),
            money(r['proposed_existing_asset_redeployment_amount'],r['holding_gap_currency']),
            money(r['proposed_new_external_buy_amount'],r['new_external_currency']),
            money(r['sell_recommendation'].get('amount'),r['sell_recommendation'].get('currency',r['holding_gap_currency'])),r['reason']])
    intro=['第04項持股建議報告已完成；逐檔無法判定的部分已明列。',
        '¹ 依已確認持股計算，尚未扣除本人既有未成交委託。持股缺口不等於本次立即應買金額。',
        '² 新增外部資金與既有現金／資產重新部署分開列示；0只表示該欄的試算金額，不代表全部不買。',
        '未產生原生賣出金額者標為未定；不將目標超配直接當作賣出指示。',
        '掛單扣除後淨額待確認；其他判斷、缺口與Mentor已交付。']
    if (report.get('new_investment_scenario') or {}).get('total_new_investment_amount')=='0':
        intro.insert(1,'本輪不新增外部資金，新增投入為0；既有現金與持倉保留。')
    tactical=next((p['current_analysis'].get('v70_tactical_budget') for p in positions if p['current_analysis'].get('v70_tactical_budget')),None)
    if tactical:intro.append('原V70股票戰術總額度：'+str(tactical['allocation']['sTot'])+'%，'+money(tactical['amounts']['stock'],tactical['currency'])+'；此為股票總池額度，非單檔補倉金額。')
    markdown='\n\n'.join(intro)+'\n\n| '+' | '.join(headings)+' |\n| '+' | '.join(['---']*len(headings))+' |\n'
    markdown+='\n'.join('| '+' | '.join(str(v).replace('|','／').replace('\n',' ') for v in row)+' |' for row in cells)
    markdown+='\n\n'+ '\n\n'.join('### '+r['symbol']+'｜'+str(r['market_date'] or '行情日期未定')+'\n\n'+r['mentor_explanation'] for r in rows)
    body=''.join('<p>'+escape(x)+'</p>' for x in intro)+'<table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headings)+'</tr></thead><tbody>'
    body+=''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in cells)+'</tbody></table>'
    body+=''.join('<details><summary>'+escape(r['symbol'])+'｜Mentor與來源日期 '+escape(r['market_date'] or '未定')+'</summary><pre>'+escape(r['mentor_explanation'])+'</pre></details>' for r in rows)
    html='<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第04項持股建議</title><style>body{font:16px system-ui;margin:24px;color:#182333}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd4df;text-align:left;vertical-align:top}th{background:#edf3fa}pre{white-space:pre-wrap}details{margin-top:16px}tr:nth-child(even){background:#f7f9fc}</style>'+body+'</html>'
    out={'schema_version':'Family.W8.RecommendationReport.v1','status':'REPORT_COMPLETE_WITH_LIMITATIONS',
        'report_delivery_status':'COMPLETE','scope':'SELECTED_IB_HOLDINGS_RECOMMENDATIONS',
        'client_id':request['client_id'],'run_id':request['run_id'],'positions_returned':len(rows),
        'net_after_orders_status':'PENDING_OWNER_ORDER_CONFIRMATION',
        'analysis_status':report['status'],'full_native_deployment_complete':False,
        'rows':rows,'markdown':markdown,'html':html,'trade_action':'NO_TRADE'}
    out['digest']=digest(out)
    return out
