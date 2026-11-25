"""Synthetic account-scoped Menu04 receipts and earlier V75 references."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("holdings_html_fixture", HERE / "fixtures/report_html/synthetic.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
W6 = F.load("holdings_on_demand_test", "on_demand_w6.py")


def seal(c):
    q, r = c["request"], c["result"]
    r["request_digest"] = F.A.digest(q)
    for row in r["analysis_result"]["positions"]:
        d = row["current_analysis"]
        d["delivery_digest"] = F.A.digest({k: v for k, v in d.items() if k != "delivery_digest"})
    wr = r["work9_request"]
    wr["request_digest"] = r["request_digest"]
    wr["positions"] = [{"instrument_id": x["instrument_id"], "native_component_delivery": deepcopy(x["current_analysis"])}
                       for x in r["analysis_result"]["positions"]]
    w9 = r["work9_result"]
    w9["source_request_digest"] = F.A.digest(wr)
    w9["request_digest"] = r["request_digest"]
    w9["result_digest"] = F.A.digest({k: v for k, v in w9.items() if k != "result_digest"})
    r["mentor"]["source_result_digest"] = F.A.digest(w9)
    for item in r["mentor"].get("items", []):
        item["source_result_digest"] = w9["result_digest"]
    rr = r["recommendation_report"]
    rr["digest"] = F.A.digest({k: v for k, v in rr.items() if k != "digest"})
    r["manifest_digest"] = F.A.digest(r["manifest"])
    r["report_digest"] = F.A.digest({k: v for k, v in r.items() if k not in ("report_digest", "source_sha256")})


def documents(raw, structural):
    return {name: {"source_id": "SYNTHETIC_REFERENCE_" + name,
                   "original_text": json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                   "sha256": sha256((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()).hexdigest()}
            for name, value in (("raw", raw), ("structural", structural))}


def case():
    base = F.case()
    q = deepcopy(base["request"])
    q["analysis_permission"] = "ANALYZE_ONLY"
    q["run_id"] = "synthetic-account-holdings"
    common = {"client_id": F.CLIENT, "run_id": q["run_id"], "owner": deepcopy(q["owner"]),
              "source_db_sha256": base["source"]["source_db_sha256"]}
    holding = {"quantity": "4", "quantity_state": "KNOWN", "observed_at": F.ASOF}
    delivery = {"owner": deepcopy(q["owner"]), "symbol": "KEEP", "holding": deepcopy(holding)}
    row = {"instrument_id": "KEEP", "symbol": "KEEP", "owner": deepcopy(q["owner"]),
           "status": "ANALYSIS_PARTIAL", "holding": holding, "current_analysis": delivery,
           "market": {"observed_date": "2026-10-29", "observed_close": "7.125"}}
    wreq = {**deepcopy(common), "positions": []}
    work9 = {**deepcopy(common), "full_canonical_deployment_complete": False, "trade_action": "NO_TRADE",
             "items": [{"item_id": "KEEP", "asset_id": "KEEP", "native_component_delivery": delivery}]}
    mentor = {**deepcopy(common), "full_native_deployment_mentor": False, "broker_execution_allowed": False,
              "production": "HOLD", "trade_action": "NO_TRADE", "items": [{"item_id": "KEEP", "asset_id": "KEEP"}]}
    recommendation = {"client_id": F.CLIENT, "run_id": q["run_id"], "positions_returned": 1,
                      "full_native_deployment_complete": False, "trade_action": "NO_TRADE", "rows": [
                          {"instrument_id": "KEEP", "symbol": "KEEP", "quantity": "4",
                           "proposed_existing_asset_redeployment_amount": None, "proposed_new_external_buy_amount": "0",
                           "native_cash_trial_buy_amount": None, "new_external_currency": "TWD"}]}
    bond = {**deepcopy(common), "canonical_result": None, "full_native_canonical_complete": False,
            "trade_action": "NO_TRADE", "status": "ORIGINAL_SOURCE_WITH_GAPS", "requested_instruments": ["KEEP"],
            "targets": {"KEEP": {}, "NEW": {}}, "structural_state": {
                "run_id": q["run_id"], "broker_account_id": q["owner"]["account"], "currency": q["owner"]["currency"],
                "gap_calculations": [{"asset_id": "KEEP", "remaining_target_gap_amount": {
                    "status": "KNOWN", "value": {"amount": "12", "currency": "TWD"}},
                    "eligible_existing_amount": {"status": "KNOWN", "value": {"amount": "0", "currency": "TWD"}}}]}}
    result = {"schema_version": "Family.W8.HoldingsAnalysisReport.v1", **common, "status": "ANALYSIS_PARTIAL",
              "snapshot_digest": F.A.digest(q["client_snapshot"]["payload"]), "source_data_provenance": "SOURCE_BACKED",
              "analysis_result": {"scope": "SELECTED_ACCOUNT__NOT_ALL_HOUSEHOLD", "positions": [row],
                                  "coverage": {"requested": 1, "returned": 1}},
              "deployment_status": {"full_native_canonical_complete": False}, "canonical_result": None,
              "trade_authorization": "NONE", "trade_action": "NO_TRADE", "work9_request": wreq,
              "work9_result": work9, "mentor": mentor, "recommendation_report": recommendation,
              "manifest": [], "native_bond_source": bond}
    c = {"source": base["source"], "request": q, "result": result}
    seal(c)
    raw = {"schema": "Synthetic.RawBondObservation.v1", "client_id": F.CLIENT,
           "run_id": "synthetic-earlier-reference", "evaluation_at": "2026-10-29T20:01:00Z",
           "source_pack_sha256": "d" * 64, "trade_authorization": "NONE", "has_formal_buying_permission": False,
           "bond_positions": {}}
    structural = {"schema_version": "Synthetic.StructuralReference.v1", "member_client_id": F.CLIENT,
                  "source_db_sha256": common["source_db_sha256"], "parent_raw_run_id": raw["run_id"],
                  "source_sha256": "d" * 64, "actual_evaluation_at": "2026-10-29T20:02:00Z",
                  "trade_authorization": "NONE", "formal_ledger_writable": False, "assets": {}}
    for symbol in ("KEEP", "NEW", "TW_A", "TW_B", "TW_C", "TW_D"):
        qty = "0" if symbol == "NEW" else "4"
        raw["bond_positions"][symbol] = {"symbol": symbol, "source_zip_sha256": "d" * 64,
            "last_close": "7.25", "last": "2026-10-29", "currency": "TWD", "rows": 30,
            "native_numeric": {"ma20": "7.5", "rsi14": "42"}, "native_td9": {"low": 0, "high": 2}}
        structural["assets"][symbol] = {"total_quantity": qty, "provider_close": "7.25", "valuation_currency": "TWD",
            "positions": [] if symbol == "NEW" else [{"account": "REFERENCE_ACCOUNT_A", "qty": "1"},
                                                      {"account": "REFERENCE_ACCOUNT_B", "qty": "3"}],
            "normal_increment_amount": None, "normal_increment_quantity": None,
            "full_v75_financial_permission": "UNKNOWN", "v75_pred009": {"state": "TECHNICAL_NEUTRAL"}}
    c["review_sources"] = documents(raw, structural)
    return c


def inputs(c):
    return F.A.make_holdings_review_inputs(c["source"], c["request"], c["result"],
        source_id="SYNTHETIC_NATIVE_HOLDINGS", rules_sha="e" * 64, review_sources=c.get("review_sources"))


def current(c=None):
    c = c or case()
    return F.D.build_w6_current_data(c["source"], **inputs(c))


def tw_case():
    c=case();q=c['request'];r=c['result'];snap=q['client_snapshot']['payload'];tables=snap['tables']
    owner={'client_id':F.CLIENT,'account':'SYNTH_TW_ACCOUNT','broker':'SYNTH_TW_BROKER',
           'currency':'TWD','funding_domain':'TW_LOCAL_BROKER'}
    account={'client_id':F.CLIENT,'account_key':owner['account']}
    tables['portfolio_account'].append(account)
    tables['account_broker_link']=[{'client_id':F.CLIENT,'account_key':owner['account'],'broker_key':owner['broker']}]
    for symbol,quantity in [('BOTH','7'),('SELL','9')]:
        next(x for x in tables['portfolio_instrument'] if x['ticker']==symbol)['quote_currency']='TWD'
        tables['portfolio_position'].append({'client_id':F.CLIENT,'account_key':owner['account'],
            'instrument_key':symbol,'quantity_decimal':quantity,'as_of_utc':F.ASOF})
    broker_original=[{'symbol':'BOTH','broker_label':'SYNTH_BROKER_ONE','quantity':7,'currency':'TWD'},
                     {'symbol':'BOTH','broker_label':'SYNTH_OTHER_BROKER','quantity':2,'currency':'TWD'}]
    raw={'client_id':F.CLIENT,'field_key':'SYNTHETIC_BROKER_SOURCE','value_text':json.dumps(broker_original)}
    tables['synthetic_broker_sources']=[raw]
    snap['payload_digest']=F.A.digest(tables);q['client_snapshot']['digest']=F.A.digest(snap)
    c['source']=F.S.build_report_source(snap,account='AR',expected_client_id=F.CLIENT)
    r['snapshot_digest']=F.A.digest(snap)
    registered={};market={};holdings=[]
    for symbol,quantity,value in [('BOTH','7','185.50'),('SELL','9','238.50')]:
        source_row=next(x for x in tables['portfolio_position'] if x['account_key']==owner['account'] and x['instrument_key']==symbol)
        registered[symbol]={'symbol':symbol,'instrument_key':symbol,'account_key':owner['account'],
            'quantity':quantity,'currency':'TWD','observed_at':F.ASOF,'source_row':deepcopy(source_row)}
        market[symbol]={'currency':'TWD','exchange':'TPEX','observed_session':'2026-10-29','completed_close':'26.5',
            'sessions':30,'market_available_at':F.ASOF,'expected_last_completed_session':'2026-10-29',
            'calendar_sha256':'f'*64,'missing_calendar_sessions':[],'extra_calendar_sessions':[],
            'completed_price_is_current':True,'volume_unit':'BOARD_LOTS','predicate_observations':{
                'PRED-009':{'original_result':{'aggregate_state':'TECHNICAL_NEUTRAL','assessment_status':'VALID'},
                            'metrics':{'rsi14':'42','ma20':'26.1'},'input_freshness_verified':False}}}
        holdings.append({'asset_id':symbol,'broker_account_id':owner['account'],'amount':{'amount':value,'currency':'TWD'}})
    identity={'run_id':q['run_id'],'broker_account_id':owner['account'],'currency':'TWD'}
    w3={**identity,'evaluation_state':'REVIEW_REQUIRED','work3_complete':False,'gap_calculations':[
        {'asset_id':symbol,'eligibility_state':'ELIGIBLE' if symbol=='BOTH' else 'INELIGIBLE_NEW_ALLOCATION',
         'target_amount':{'amount':'15','currency':'TWD'},'eligible_existing_amount':{'status':'KNOWN','value':h['amount']},
         'remaining_target_gap_amount':{'status':'KNOWN','value':{'amount':'0','currency':'TWD'}}}
        for symbol,h in zip(registered,holdings)]}
    output={**identity,'formal_output_eligible':False,'per_asset_decisions':[],
            'bond_allocation_final':{'account_scope':{**{k:v for k,v in identity.items() if k!='run_id'},'broker_domain_type':'TW_LOCAL_BROKER'}}}
    t={'schema_version':'Family.W8.TWLocalBondAnalysis.v1','run_id':q['run_id'],'evaluation_at':q['evaluation_at'],
       'source_db_sha256':c['source']['source_db_sha256'],'owner':owner,'account_binding':{
           'owner':deepcopy(owner),'source_rows':[deepcopy(account)],'approved_document_category_scope':{
               'owner':deepcopy(owner),'original_account_row':deepcopy(account),'source_snapshot_digest':snap['payload_digest'],
               'trade_authorization':'NONE'}},'registered_positions':registered,'market':market,
       'native_validation':{'state':'ACCEPT','accepted':True},'trade_authorization':'NONE','trade_action':'NO_TRADE',
       'formal_deployment_eligible':False,'canonical_result':None,'native_input':{
           'client_ref':F.CLIENT,**identity,'analysis_timestamp':q['evaluation_at'],'broker_domain_type':'TW_LOCAL_BROKER',
           'existing_bond_holdings':holdings,'bond_executable_budget':{'amount':'0','currency':'TWD'},
           'broker_cash_total':{'status':'UNKNOWN','value':None},'broker_cash_available':{'status':'UNKNOWN','value':None}},
       'work3':w3,'work4':{'status':'QUALIFIED_PREDICATES_AND_ACCOUNT_FUNDING_REQUIRED',
           'missing':['SYNTHETIC_SAME_ACCOUNT_CASH'],'predicate_source_gaps':{s:{'PRED-009':{'assessment_status':'VALID'}} for s in registered}},
       'work5':{'snapshot':{**identity,'output':output,'final_classification':'REVIEW_REQUIRED','gate_state':'INSUFFICIENT_DATA'}},
       'original_broker_rows':[{**x,'quantity':str(x['quantity']),'source_row':deepcopy(raw),
           'account_key':None,'account_mapping_state':'UNKNOWN','received_at':F.ASOF,'source_run_id':'SYNTHETIC_EARLIER_BROKER'}
           for x in broker_original]}
    r['tw_local_bond_analysis']=t
    documents_raw={k:json.loads(v['original_text']) for k,v in c['review_sources'].items()}
    for old,new in [('TW_A','BOTH'),('TW_B','SELL')]:
        documents_raw['raw']['bond_positions'][new]=documents_raw['raw']['bond_positions'].pop(old)
        documents_raw['raw']['bond_positions'][new]['symbol']=new
        documents_raw['structural']['assets'][new]=documents_raw['structural']['assets'].pop(old)
    c['review_sources']=documents(documents_raw['raw'],documents_raw['structural'])
    seal(c);return c


class HoldingsReviewTest(unittest.TestCase):
    def test_same_run_native_TW_is_quoted_as_native_and_older_rows_are_not_relabelled(self):
        c=tw_case();before=deepcopy(c);out=current(c);cards=out['verified_sections']['bond']
        self.assertTrue(out['report_source_lineage']['section_projection']['same_run_native_TW_present'])
        self.assertTrue(any(x['heading'].startswith('BOTH｜當輪原生臺幣逐檔結果') for x in cards))
        self.assertFalse(any(x['heading'].startswith('BOTH｜補充實持') for x in cards))
        technical=[f for card in cards for f in card.get('quoted_fields',[]) if f['pointer'].endswith('/predicate_observations/PRED-009/original_result/aggregate_state')]
        self.assertEqual(len(technical),2);self.assertTrue(all(f['present'] and f['value']=='TECHNICAL_NEUTRAL' for f in technical))
        self.assertEqual(out['report_source_lineage']['holdings_analysis'],c['result'])
        positions=out['current_position_display']['positions']
        self.assertEqual([(x['ticker'],x['quantity']) for x in positions],[('KEEP','4'),('BOTH','7'),('SELL','9')])
        self.assertEqual(len(c['result']['tw_local_bond_analysis']['original_broker_rows']),2)
        self.assertEqual(c,before)

    def test_rehashed_native_TW_wrong_run_owner_DB_quantity_work5_and_other_broker_rejected(self):
        attacks=[lambda t:t.update(run_id='OTHER'),lambda t:t.update(source_db_sha256='0'*64),
            lambda t:t['owner'].update(account='OTHER'),lambda t:t['native_input'].update(run_id='OTHER'),
            lambda t:t['registered_positions']['BOTH'].update(quantity='99'),
            lambda t:t['market']['BOTH'].update(market_available_at='2027-01-01T00:00:00Z'),
            lambda t:t['work3'].update(currency='USD'),lambda t:t['work5']['snapshot']['output'].update(run_id='OTHER'),
            lambda t:t['original_broker_rows'][1].update(account_key='SYNTH_TW_ACCOUNT'),
            lambda t:t['original_broker_rows'][1].update(quantity='999'),
            lambda t:t['native_validation'].update(accepted=False)]
        for index,attack in enumerate(attacks):
            c=tw_case();attack(c['result']['tw_local_bond_analysis']);seal(c)
            with self.subTest(attack=index),self.assertRaises(ValueError):current(c)

    def test_current_holdings_precede_historical_DB_only_in_chapter3(self):
        out=current(tw_case());blocks=F.R._build_blocks(out);legacy=deepcopy(out);legacy.pop('current_position_display')
        before=F.R._build_blocks(legacy)
        for actual,old in zip(blocks,before):
            if actual['chapter']!=3:self.assertEqual(actual,old)
        text=' '.join(blocks[2]['parts'])
        self.assertLess(text.index('KEEP｜當輪來源持倉'),text.index('歷史資料庫持倉'))
        self.assertIn('現持：4 股',text);self.assertIn('歷史數量',text)

    def test_current_holding_unknown_quantity_and_reference_amount_are_not_zero_filled(self):
        c=case();row=c['result']['analysis_result']['positions'][0]
        row['holding']['quantity']=None;row['current_analysis']['holding']['quantity']=None
        c['result']['recommendation_report']['rows'][0]['quantity']=None;seal(c)
        out=current(c);position=out['current_position_display']['positions'][0]
        self.assertIsNone(position['quantity']);self.assertIsNone(position['reference_amount'])
        text=' '.join(F.R._build_blocks(out)[2]['parts'])
        self.assertIn('現持：UNKNOWN 股',text)

    def test_original_result_and_earlier_six_references_remain_distinct(self):
        c = case(); before = deepcopy(c); out = current(c)
        self.assertEqual(c, before)
        self.assertEqual(out["report_source_lineage"]["holdings_analysis"], c["result"])
        self.assertEqual(len(out["report_source_lineage"]["holdings_review_documents"]["structural"]["assets"]), 6)
        self.assertIsNone(out["current_total_twd"])
        self.assertEqual(out["report_scope"], "SOURCE_REVIEW")
        cards = out["verified_sections"]
        text = " ".join(x["body"] for rows in cards.values() for x in rows)
        self.assertIn("UNKNOWN", text); self.assertIn("REFERENCE_ACCOUNT_A", text); self.assertIn("REFERENCE_ACCOUNT_B", text)
        fields = [f for rows in cards.values() for card in rows for f in card.get("quoted_fields", [])]
        self.assertTrue(any(f["pointer"].endswith("/total_quantity") and f["value"] == "0" for f in fields))
        self.assertTrue(any(f["pointer"].endswith("/normal_increment_amount") and f["value"] is None for f in fields))
        self.assertTrue(any(f["pointer"].endswith("/proposed_new_external_buy_amount") and f["value"] == "0" for f in fields))

    def test_original_report_without_supplement_does_not_invent_six_account_results(self):
        c = case(); c["review_sources"] = None
        out = current(c)
        self.assertEqual(out["report_source_lineage"]["holdings_review_documents"], {})
        self.assertEqual(out["report_source_lineage"]["holdings_analysis"], c["result"])

    def test_long_identifiers_are_wrapped_with_display_whitespace_only(self):
        c=case();long_scope="SYNTHETIC_SCOPE_"*20
        c["result"]["analysis_result"]["scope"]=long_scope;seal(c)
        out=current(c);cards=out["verified_sections"]["bond"]
        fact=next(f for card in cards for f in card.get("quoted_fields",[]) if f["pointer"]=="/result/analysis_result/scope")
        self.assertEqual(fact["value"],long_scope)
        self.assertTrue(any(long_scope in card["body"].replace(" ","") for card in cards))
        self.assertFalse(any(long_scope in card["body"] for card in cards))

    def test_operator_constructor_accepts_only_pinned_pair_and_keeps_original_options(self):
        c = case(); pair = {k: c[k] for k in ("request", "result")}
        options = {"source_id": "SYNTHETIC_RECEIVER", "rules_sha": "e" * 64,
                   "expected_request_digest": F.A.digest(c["request"]), "expected_result_digest": F.A.digest(c["result"]),
                   "holdings_review_sources": c["review_sources"]}
        producer = W6.MemberAnalysisReportProducer.from_menu04(pair, **options)
        self.assertEqual(producer(c["source"], {})["engine"]["report_sources"]["result"], c["result"])
        with self.assertRaisesRegex(ValueError, "W6_MENU04_RECEIPT_DIGEST_MISMATCH"):
            W6.MemberAnalysisReportProducer.from_menu04(pair, **{**options, "expected_result_digest": "f" * 64})
        producer.sections = {}
        with self.assertRaisesRegex(ValueError, "W6_HOLDINGS_REVIEW_SOURCE_OPTIONS_CONFLICT"):
            producer(c["source"], {})

    def test_rehashed_wrong_identity_account_DB_run_content_or_mentor_rejected(self):
        attacks = [lambda c: c["request"].update(client_id="OTHER"),
            lambda c: c["result"].update(source_db_sha256="f" * 64),
            lambda c: c["result"].update(run_id="OTHER"),
            lambda c: c["result"]["owner"].update(account="OTHER"),
            lambda c: c["result"]["analysis_result"]["positions"][0]["current_analysis"].update(symbol="OTHER"),
            lambda c: c["result"]["work9_result"]["items"][0].update(asset_id="OTHER"),
            lambda c: c["result"]["mentor"].update(owner={}),
            lambda c: c["result"]["mentor"].update(broker_execution_allowed=True),
            lambda c: c["result"]["recommendation_report"]["rows"][0].update(quantity="5"),
            lambda c: c["result"]["native_bond_source"]["structural_state"].update(run_id="OTHER")]
        for i, attack in enumerate(attacks):
            with self.subTest(attack=i):
                c = case(); attack(c); seal(c)
                with self.assertRaises(ValueError): current(c)

    def test_each_original_document_bytes_are_verified_including_whitespace(self):
        for kind in ("raw", "structural"):
            c = case(); c["review_sources"][kind]["original_text"] += "\n"
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "W6_HOLDINGS_REVIEW_DOCUMENT_SHA"):
                current(c)

    def test_future_holdings_market_and_mismatched_mentor_items_rejected(self):
        for attack in (lambda c: c["result"]["analysis_result"]["positions"][0]["holding"].update(observed_at="2027-01-01T00:00:00Z"),
                       lambda c: c["result"]["analysis_result"]["positions"][0]["market"].update(observed_date="2027-01-01"),
                       lambda c: c["result"]["mentor"]["items"][0].update(asset_id="OTHER")):
            c=case();attack(c);seal(c)
            with self.subTest(attack=attack),self.assertRaises(ValueError):current(c)

    def test_each_document_identity_time_source_price_currency_and_zero_scope_checked(self):
        attacks = [("raw", lambda d: d.update(client_id="OTHER")),
            ("structural", lambda d: d.update(source_db_sha256="f" * 64)),
            ("structural", lambda d: d.update(parent_raw_run_id="OTHER")),
            ("structural", lambda d: d.update(actual_evaluation_at="2026-11-01T00:00:00Z")),
            ("raw", lambda d: d.update(has_formal_buying_permission=True)),
            ("raw", lambda d: d["bond_positions"]["KEEP"].update(last_close="8")),
            ("raw", lambda d: d["bond_positions"]["KEEP"].update(currency="USD")),
            ("structural", lambda d: d["assets"]["KEEP"].update(normal_increment_quantity="0")),
            ("structural", lambda d: d["assets"]["KEEP"]["positions"][1].update(account="REFERENCE_ACCOUNT_A")),
            ("structural", lambda d: d["assets"]["KEEP"].update(total_quantity="9"))]
        for i, (kind, attack) in enumerate(attacks):
            c = case(); docs = {k: json.loads(v["original_text"]) for k, v in c["review_sources"].items()}
            attack(docs[kind]); c["review_sources"] = documents(docs["raw"], docs["structural"])
            with self.subTest(attack=i), self.assertRaises(ValueError): current(c)

    def test_complete_analysis_does_not_promote_partial_deployment_to_canonical(self):
        c = case(); c["result"]["status"] = "ANALYSIS_COMPLETE"; seal(c)
        self.assertEqual(current(c)["report_scope"], "SOURCE_REVIEW")
        i = inputs(c); binding = i["engine"]["report_sources"]
        binding["scope"] = "CANONICAL_CALCULATION"
        binding["digest"] = F.A.digest({k: v for k, v in binding.items() if k != "digest"})
        with self.assertRaisesRegex(ValueError, "W6_HOLDINGS_REVIEW_SCOPE_ONLY"):
            F.D.build_w6_current_data(c["source"], **i)
        self.assertEqual(F.current()["report_scope"], "CANONICAL_CALCULATION")


if __name__ == "__main__":
    unittest.main()
