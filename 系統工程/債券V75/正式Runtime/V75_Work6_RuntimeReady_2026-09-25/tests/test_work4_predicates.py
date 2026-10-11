from datetime import datetime,timezone
from v75_runtime.predicates import *
N=datetime(2026,9,25,tzinfo=timezone.utc); L=['test']
def test_predicate_smoke():
 assert pred001({'effr_pct':5,'effr_10y_percentile_pct':95,'sep_long_run_median_pct':2.5,'core_pce_yoy_pct':2.5},N,L).aggregate_state=='EXTREME'
 assert pred002({'expected_policy_rate_6m_delta_5bd_bps':55},N,L).aggregate_state=='EXTREME_HAWKISH_REPRICING'
 assert pred003({'yield_delta_5bd_bps':40,'yield_delta_10bd_bps':65,'yield_up_days_last5':4},N,L).aggregate_state=='EXTREME_RISE'
 assert pred004({'hy_oas_bps':850,'hy_oas_delta_20bd_bps':220,'ig_oas_delta_20bd_bps':35},N,L).aggregate_state=='CREDIT_CRISIS'
 assert pred005({'move':155,'move_pct_change_5bd':5},N,L).aggregate_state=='EXTREME'
 assert pred006({'core_pce_ann3_pct':4.2,'core_pce_ann6_pct':3.2,'core_cpi_ann3_pct':4.1,'core_cpi_ann6_pct':3.0,'core_ppi_ann3_pct':2,'core_ppi_ann6_pct':2,'breakeven_5y_pct':2.5,'oil_price_change_20bd_pct':5},N,L).aggregate_state=='LOSS_OF_CONTROL'
 assert pred007({'sofr_ois_bps':5,'fra_ois_bps':5,'srf_usage_usd':0},N,L).aggregate_state=='NORMAL'
 assert pred008({'yield_percentile_pct':92,'history_years':5},N,L).aggregate_state=='VERY_ATTRACTIVE'
 assert pred009({'low_td_count':6,'k':15,'d':18,'rsi14':28,'close':90,'ma20':100,'ma50':105,'rolling_20d_low':88,'atr14':3},N,L).aggregate_state=='LEFT_MATURE'
 assert pred010({'structure_state':'STRUCTURE_OK','liquidity_state_etf':'LIQUIDITY_OK','distribution_quality_state':'DISTRIBUTION_OK'},N,L).aggregate_state=='ETF_QUALITY_NORMAL'
