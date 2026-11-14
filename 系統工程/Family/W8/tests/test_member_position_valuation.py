"""Dated partial valuation does not create NAV, new cash or missing weights."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import digest
from member_position_valuation import produce,read_fx
from official_holdings_source import project_official_holdings
from test_owner_source_recovery import corrected_snapshot


def fx_case(tmp_path):
    raw=('牌價最新掛牌時間：<span class="time">2026/11/03 11:56</span>'
        '<table><tr><td>美金 (USD)</td><td data-table="本行即期買入">32.715</td>'
        '<td data-table="本行即期賣出">32.815</td></tr></table>').encode()
    path=tmp_path/'quote.html';path.write_bytes(raw)
    return dict(local_path=str(path),sha256=sha256(raw).hexdigest(),
        source_reference='https://rate.bot.com.tw/xrt?Lang=zh-TW',retrieved_at='2026-11-03T04:00:00Z')


def case(tmp_path):
    snap=corrected_snapshot();at='2026-11-03T04:00:00Z'
    snap['tables']['portfolio_snapshot_item'].append(dict(client_id=snap['client_id'],run_id='CORRECTION',
        domain_code='CASH',entity_key='TWD',field_key='owner_reported_amount',value_state='KNOWN',
        value_text='100000',currency_code='TWD',source_observed_at_utc='2026-10-26T01:00:00Z'))
    snap['payload_digest']=digest(snap['tables'])
    fact=project_official_holdings(snap,evaluation_at=at)['analysis_security_positions'][0]
    request=dict(client_id=snap['client_id'],run_id='SYNTHETIC_RUN',evaluation_at=at,client_snapshot=dict(payload=snap))
    coverage=dict(client_id=snap['client_id'],source_db_sha256=snap['source_sha256'],evaluation_at=at,
        bonds=[],holding_and_target_rows=[dict(symbol='TEST',source_facts=[fact])],
        cash_accounts=[dict(account_key='SOURCE_ONE',reported_cash='100000'),dict(account_key='SOURCE_TWO',reported_cash='100000')])
    coverage['coverage_digest']=digest(coverage)
    market=dict(observed_date='2026-11-02',observed_close='51.56',source_sha256='b'*64,
        market_identity=dict(currency='USD'),history_quality=dict(price_basis='SYNTHETIC_PROVIDER_QUOTE'))
    return request,coverage,[dict(symbol='TEST',market=market)],dict(fx_source=fx_case(tmp_path))


def test_corrected_quantity_is_valued_without_summing_duplicate_reported_cash(tmp_path):
    request,coverage,rows,inputs=case(tmp_path);out=produce(request,coverage,rows,inputs)
    assert out['positions'][0]['amount']=='154.68'
    assert out['positions'][0]['reporting_amount_TWD']=='5060.35620'
    assert out['latest_owner_cash_reports'][0]['amount']=='100000'
    assert len(out['cash_account_sources'])==2 and not out['cash_sources_assumed_independent']
    assert out['qualified_portfolio_NAV'] is None and out['deployable_cash'] is None and out['new_buy_amount'] is None


@pytest.mark.parametrize('quote',['32.715','32.716'])
def test_bank_screen_and_print_quote_cells_must_agree(tmp_path,quote):
    source=fx_case(tmp_path);path=Path(source['local_path'])
    path.write_text(path.read_text().replace('</tr>','<td data-table="本行即期買入">'+quote+'</td></tr>'))
    source['sha256']=sha256(path.read_bytes()).hexdigest()
    if quote=='32.715':assert read_fx(source,'2026-11-03T04:00:00Z')['quote_per_base']=='32.715'
    else:
        with pytest.raises(ValueError):read_fx(source,'2026-11-03T04:00:00Z')


@pytest.mark.parametrize('issue',['missing_quantity','currency_conflict','missing_market','duplicate_position'])
def test_missing_or_ambiguous_inputs_do_not_invent_values(tmp_path,issue):
    req,cov,rows,inputs=case(tmp_path)
    if issue=='missing_quantity':cov['holding_and_target_rows'][0]['source_facts'][0]['quantity']=None
    elif issue=='currency_conflict':rows[0]['market']['market_identity']['currency']='CAD'
    elif issue=='missing_market':rows[0]['market']=None
    else:cov['holding_and_target_rows'][0]['source_facts']*=2
    cov['coverage_digest']=digest({k:v for k,v in cov.items() if k!='coverage_digest'})
    out=produce(req,cov,rows,inputs)
    assert all(r['amount'] is None and r['issue'] for r in out['positions'])


@pytest.mark.parametrize('issue',['cross_member','changed_db','old_cutoff','changed_coverage'])
def test_valuations_bind_to_same_member_db_and_evaluation(tmp_path,issue):
    req,cov,rows,inputs=case(tmp_path)
    if issue=='cross_member':cov['client_id']='SYNTHETIC_OTHER'
    elif issue=='changed_db':req['client_snapshot']['payload']['source_sha256']='c'*64
    elif issue=='old_cutoff':cov['evaluation_at']='2026-11-02T00:00:00Z'
    else:cov['cash_accounts'].append({'account_key':'INJECTED'})
    with pytest.raises(PermissionError):produce(req,cov,rows,inputs)


@pytest.mark.parametrize('issue',['changed_bytes','future_quote','wrong_source'])
def test_bank_reference_is_original_dated_fx_not_assumed_cash(tmp_path,issue):
    source=fx_case(tmp_path)
    if issue=='changed_bytes':Path(source['local_path']).write_text('CHANGED')
    elif issue=='future_quote':source['retrieved_at']='2026-11-03T03:00:00Z'
    else:source['source_reference']='https://example.invalid/quote'
    with pytest.raises((ValueError,PermissionError)):read_fx(source,'2026-11-03T04:00:00Z')
