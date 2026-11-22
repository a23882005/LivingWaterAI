"""Invented source receipts: known zero, missing values and report-only scope."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("report_zero_fixture", HERE / "fixtures/report_html/synthetic.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
W6 = F.load("report_zero_on_demand", "on_demand_w6.py")


def seal(case):
    result = case["result"]
    result["request_digest"] = F.A.digest(case["request"])
    for row in result["positions"]:
        conclusion = row.get("formal_conclusion")
        if conclusion is not None:
            conclusion["binding"]["request_digest"] = result["request_digest"]
            if "conclusion_digest" in conclusion:
                conclusion["conclusion_digest"] = F.A.digest({k: v for k, v in conclusion.items() if k != "conclusion_digest"})
        scoped = row.get("owner_scoped_financial_result")
        if scoped is not None:
            rule = scoped["owner_rule"]
            rule["digest"] = F.A.digest({k: v for k, v in rule.items() if k != "digest"})
            if "result_digest" in scoped:
                scoped["result_digest"] = F.A.digest({k: v for k, v in scoped.items() if k != "result_digest"})
    F.member_refresh(case)


def zero_case(kind):
    case = F.member_case()
    source, request, result = (case[k] for k in ("source", "request", "result"))
    row = result["positions"][0]
    symbol = row["symbol"]
    binding = {"client_id": F.CLIENT, "run_id": request["run_id"],
               "evaluation_at": request["evaluation_at"], "source_db_sha256": source["source_db_sha256"]}
    price = {k: v for k, v in binding.items() if k != "source_db_sha256"}
    price.update(symbol=symbol, currency="USD", source_sha256="c" * 64, session="2026-10-29")
    row.update(proposed_amount={"amount": "0", "currency": "USD"}, proposed_quantity="0",
               same_run_gap_price=price, market={"source_sha256": "c" * 64,
                   "observed_date": "2026-10-29", "market_identity": {"currency": "USD"}})
    row["formal_conclusion"].update(schema_version="Family.W8.FormalModeConclusion.v1",
        formal_stage="UNKNOWN", selected_mode="UNKNOWN", stage_required_unknown_fields=["SYNTHETIC_MISSING_FACT"],
        trade_action="NO_TRADE", buy_permission={"broker_trade_authorization": "NONE"}, conclusion_digest="")
    if kind == "pause":
        signals = {"down_break": [{"name": "SYNTHETIC_BREAK", "truth": "TRUE"}],
                   "down_accel": [{"name": "SYNTHETIC_ACCEL_A", "truth": "TRUE"},
                                  {"name": "SYNTHETIC_ACCEL_B", "truth": "TRUE"}]}
        row["market"] = {"source_sha256": "c" * 64, "observed_date": "2026-10-29",
            "market_identity": {"currency": "USD"}, "v82_original_aggregation": {"runaway_down": "TRUE"},
            "approved_technical": {"signals": signals}}
        row["core_observation"] = {"result": {"technical": {"runaway_down": "TRUE"}}}
        row["normal_buy_pause"] = {"status": "NORMAL_NEW_BUYS_PAUSED", "rule": "V82 CMR7 / 44-A / 44-E",
            "run_id": request["run_id"], "evaluation_at": request["evaluation_at"], "symbol": symbol,
            "source_sha256": "c" * 64, "position_valuation_source_sha256": "c" * 64, "session": "2026-10-29",
            "votes": {k: [x["name"] for x in rows] for k, rows in signals.items()},
            "amount": deepcopy(row["proposed_amount"]), "quantity": "0", "sell_intent_created": False,
            "target_and_gap_preserved": True}
    else:
        account = request["client_snapshot"]["payload"]["tables"]["portfolio_account"][0]
        owner = {"client_id": F.CLIENT, "account": account["account_key"], "broker": "SYNTHETIC_BROKER",
                 "currency": "USD", "funding_domain": "INVESTMENT"}
        scoped = {"schema_version": "Family.W8.OwnerQQQFinancial.v1", **binding, "asset_id": symbol,
            "owner": owner, "rule_id": "SYNTHETIC_APPROVED_SCOPE",
            "owner_rule": {**binding, "asset_id": symbol, "owner": deepcopy(owner), "member": source["member_alias"],
                           "rule_id": "SYNTHETIC_APPROVED_SCOPE", "trade_authorization": "NONE", "digest": ""},
            "status": "SCOPED_FINANCIAL_COMPLETE_NO_NEW_BUY", "known_zero_basis": "NO_POSITIVE_DEPLOYMENT_GAP",
            "canonical_quote_proof": {"valuation": deepcopy(price),
                "position": {"owner": deepcopy(owner), "symbol": symbol, "currency": "USD"}},
            "position_gap": {"positive_deployment_gap": "0", "final_deployment_gap_amount": "-20"},
            "execution_plan": {"action": "NO_NEW_BUY", "maximum_allowed_buy_amount": "0",
                "execution_amount": "0", "execution_quantity": "0",
                "order_plan": {"should_place_order": False, "order_intent_id": None, "quantity": "0"}},
            "selected_stage": "STAGE_1", "final_amount": deepcopy(row["proposed_amount"]), "final_quantity": "0",
            "full_family_native_pipeline_complete": False, "formal_deployment_ready": False,
            "trade_action": "NO_TRADE", "production": "HOLD",
            "test_ledger": {"new_cycles": 0, "new_intents": 0, "before": {"cycles": 0},
                            "after": {"cycles": 0}, "broker_cash_reserved": False}, "result_digest": ""}
        row["owner_scoped_financial_result"] = scoped
        row["financial_source_attempt"] = {"schema_version": "Family.W8.MemberFinancialProducerAttempt.v1",
            **binding, "asset_id": symbol, "owner_scoped_financial_result": scoped,
            "target_version": request["confirmed_target"]["target_version"],
            "status": scoped["status"], "qualified_financial_pack": False, "trade_action": "NO_TRADE",
            "same_run_source_binding": {**{k: v for k, v in binding.items() if k != "evaluation_at"},
                                        "target_version": request["confirmed_target"]["target_version"]},
            "account_analysis_binding": {"owner": deepcopy(owner), "approved_document_category_scope": {
                "schema_version": "Family.W5.DocumentAccountScope.v1", "owner": deepcopy(owner),
                "trade_authorization": "NONE", "source_snapshot_digest": source["snapshot_payload_sha256"],
                "original_account_row": deepcopy(account)}}}
    seal(case)
    return case


def incomplete_case():
    """Native unfinished shape: no quote, final amount/quantity or own digest."""
    case = zero_case("scoped")
    row = case["result"]["positions"][0]
    row["proposed_amount"] = None
    row.pop("proposed_quantity")
    row.pop("same_run_gap_price")
    scoped = row["owner_scoped_financial_result"]
    for key in ("canonical_quote_proof", "position_gap", "execution_plan", "selected_stage",
                "final_amount", "final_quantity", "known_zero_basis", "test_ledger", "result_digest"):
        scoped.pop(key)
    scoped.update(status="SOURCE_INCOMPLETE", missing_inputs=[{
        "field": "qualified_USD_valuation_price_and_confirmed_quantity"}])
    row["financial_source_attempt"]["status"] = scoped["status"]
    seal(case)
    return case


def dual_source_pause_case():
    """Invented independent histories with the same last-session identity."""
    case = zero_case("pause"); row = case["result"]["positions"][0]
    market, price, pause = row["market"], row["same_run_gap_price"], row["normal_buy_pause"]
    market.update(symbol=row["symbol"], source_sha256="d" * 64, observed_close="63.125", rows=41,
        provider_verified_at="2026-10-29T14:00:00Z")
    market["market_identity"]["exchange"] = "XTSY"
    market["market_identity"]["provider_symbol"] = row["symbol"]
    price.update(observed_close="63.1250", exchange="XTSY", scope="CURRENT_POSITION_EXPOSURE_ONLY")
    pause["source_sha256"] = "d" * 64
    row["core_observation"]["source_sha256"] = "d" * 64
    position = deepcopy(market)
    position.update(source_sha256="c" * 64, rows=19, provider_verified_at="2026-10-29T13:00:00Z")
    for observation in (market, position):
        observation["provider_completion_evidence"] = {
            "provider": "IBKR_LAST_DAILY_OBSERVATION", "original_document_sha256": observation["source_sha256"],
            "contract_id": 12345, "provider_exchange": "SYNTHETIC_EXCHANGE",
            "query": {"contract_id": 12345, "exchange": "SYNTHETIC_EXCHANGE", "outside_rth": False},
            "retrieved_at": observation["provider_verified_at"], "returned_end": observation["observed_date"],
            "returned_rows": observation["rows"], "independent_identity_sha256": "f" * 64}
    market["position_valuation_observation"] = position
    seal(case)
    return case


class SourceZeroTests(unittest.TestCase):
    def inputs(self, case):
        return F.A.make_member_review_inputs(case["source"], case["request"], case["result"],
                                            source_id="SYNTHETIC_ZERO_SOURCE", rules_sha="e" * 64)

    def current(self, case):
        return F.D.build_w6_current_data(case["source"], **self.inputs(case))

    def test_two_source_zero_kinds_preserve_raw_and_missing_values(self):
        for kind in ("scoped", "pause"):
            with self.subTest(kind=kind):
                case = zero_case(kind); before = deepcopy(case)
                current = self.current(case)
                self.assertEqual(case, before)
                self.assertEqual(current["report_source_lineage"]["member_analysis"], case["result"])
                self.assertEqual(current["report_scope"], "SOURCE_REVIEW")
                self.assertIsNone(current["current_total_twd"])
                self.assertEqual(current["actual"], [])
                self.assertEqual(current["drift"], [])
                self.assertIsNone(current["approved_radar"])
                cards = current["verified_sections"]
                text = "\n".join(x["body"] for x in cards["valuation"] + cards["actions"])
                self.assertIn("原新增股數：0", text)
                self.assertIn("原正式階位：UNKNOWN", text)
                self.assertIn("STAGE_1" if kind == "scoped" else "NORMAL_NEW_BUYS_PAUSED", text)
                if kind == "pause": self.assertIn("已建立賣出意圖：FALSE", text)
                self.assertIsNone(case["result"]["positions"][1]["proposed_amount"])
                self.assertEqual(set(cards), set(F.A.SECTION_NAMES))

    def test_distinct_source_hashes_preserve_original_zero_and_both_receipts(self):
        case = dual_source_pause_case(); before = deepcopy(case)
        current = self.current(case)
        self.assertEqual(case, before)
        self.assertEqual(current["report_source_lineage"]["member_analysis"], case["result"])
        self.assertEqual(current["report_source_lineage"]["section_projection"]["scoped_zero_display"]["decisions"],
            {case["result"]["positions"][0]["symbol"]: "NORMAL_NEW_BUYS_PAUSED"})
        self.assertIsNone(current["current_total_twd"])
        self.assertEqual(current["report_scope"], "SOURCE_REVIEW")

    def test_distinct_source_identity_price_date_exchange_or_currency_mismatch_rejected(self):
        for component in ("price", "market", "position"):
            for key, value in (("symbol", "FOREIGN"), ("provider_symbol", "FOREIGN"), ("exchange", "XBAD"), ("currency", "TWD"),
                               ("date", "2026-10-28"), ("close", "63.126")):
                if key == "provider_symbol" and component == "price":
                    continue
                with self.subTest(component=component, key=key):
                    case = dual_source_pause_case(); row = case["result"]["positions"][0]
                    node = row["same_run_gap_price"] if component == "price" else row["market"]
                    if component == "position": node = node["position_valuation_observation"]
                    if key in ("exchange", "currency", "provider_symbol") and component != "price": node["market_identity"][key] = value
                    else: node[{"date": "session" if component == "price" else "observed_date", "close": "observed_close"}.get(key,key)] = value
                    seal(case)
                    with self.assertRaises(ValueError): self.inputs(case)

    def test_each_distinct_sha_must_match_its_own_original_receipt_and_role(self):
        for attack in ("price_sha", "market_sha", "pause_sha", "valuation_sha", "position_sha", "core_sha",
                       "market_document_sha", "position_document_sha", "missing_position", "missing_market_proof", "missing_position_proof"):
            with self.subTest(attack=attack):
                case = dual_source_pause_case(); row = case["result"]["positions"][0]
                market = row["market"]; position = market["position_valuation_observation"]
                if attack == "price_sha": row["same_run_gap_price"]["source_sha256"] = "e" * 64
                elif attack == "market_sha": market["source_sha256"] = "e" * 64
                elif attack == "pause_sha": row["normal_buy_pause"]["source_sha256"] = "e" * 64
                elif attack == "valuation_sha": row["normal_buy_pause"]["position_valuation_source_sha256"] = "e" * 64
                elif attack == "position_sha": position["source_sha256"] = "e" * 64
                elif attack == "core_sha": row["core_observation"]["source_sha256"] = "e" * 64
                elif attack.endswith("document_sha"):
                    (market if attack.startswith("market") else position)["provider_completion_evidence"]["original_document_sha256"] = "e" * 64
                elif attack == "missing_position": market.pop("position_valuation_observation")
                else: (market if attack == "missing_market_proof" else position).pop("provider_completion_evidence")
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_distinct_source_contract_capture_and_original_44E_are_required(self):
        for key, value in (("contract_id", 12346), ("provider_exchange", "FOREIGN"),
                ("independent_identity_sha256", "e" * 64), ("retrieved_at", "2030-01-01T00:00:00Z"),
                ("returned_end", "2026-10-28"), ("returned_rows", 0), ("provider", "UNVERIFIED")):
            with self.subTest(key=key):
                case = dual_source_pause_case(); position = case["result"]["positions"][0]["market"]["position_valuation_observation"]
                proof = position["provider_completion_evidence"]; proof[key] = value
                if key == "contract_id": proof["query"]["contract_id"] = value
                if key == "retrieved_at": position["provider_verified_at"] = value
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)
        for attack in ("down", "vote", "sell", "amount", "scope"):
            with self.subTest(attack=attack):
                case = dual_source_pause_case(); row = case["result"]["positions"][0]
                if attack == "down": row["core_observation"]["result"]["technical"]["runaway_down"] = "FALSE"
                elif attack == "vote": row["normal_buy_pause"]["votes"]["down_accel"] = []
                elif attack == "sell": row["normal_buy_pause"]["sell_intent_created"] = True
                elif attack == "amount": row["proposed_amount"]["amount"] = "1"
                else: row["same_run_gap_price"]["scope"] = "ORDER_EXECUTION"
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_same_source_rich_price_receipt_cannot_disagree_on_price(self):
        case = dual_source_pause_case(); row = case["result"]["positions"][0]
        row["same_run_gap_price"]["source_sha256"] = row["market"]["source_sha256"]
        row["normal_buy_pause"]["position_valuation_source_sha256"] = row["market"]["source_sha256"]
        seal(case); self.current(case)
        row["same_run_gap_price"]["observed_close"] = "63.126"; seal(case)
        with self.assertRaises(ValueError): self.inputs(case)

    def test_distinct_source_invalid_numeric_values_or_proof_shapes_rejected(self):
        for value in (False, "0", "-1", "NaN", "Infinity", None):
            with self.subTest(close=value):
                case = dual_source_pause_case(); case["result"]["positions"][0]["same_run_gap_price"]["observed_close"] = value
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)
        for attack in ("identity", "proof", "query", "outside_rth", "boolean_count"):
            with self.subTest(attack=attack):
                case = dual_source_pause_case(); market = case["result"]["positions"][0]["market"]
                if attack == "identity": market["market_identity"] = {}
                elif attack == "proof": market["provider_completion_evidence"] = None
                elif attack == "query": market["provider_completion_evidence"]["query"] = None
                elif attack == "outside_rth": market["provider_completion_evidence"]["query"]["outside_rth"] = True
                else: market["provider_completion_evidence"]["returned_rows"] = True
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_original_blank_rows_and_old_display_are_exact(self):
        case = F.member_case()
        original = F.A._runtime("report_financial_sections", "W8").member_sections(
            case["source"], case["request"], case["result"],
            {"source_id": "SYNTHETIC_ZERO_SOURCE", "rules_sha": "e" * 64})
        current = self.current(case)
        for name in F.A.SECTION_NAMES:
            self.assertEqual(current["verified_sections"][name][0]["heading"], "資料狀態：PARTIAL")
            self.assertEqual(current["verified_sections"][name][1:], original["envelopes"][name]["payload"])
        self.assertNotIn("scoped_zero_display", current["report_source_lineage"]["section_projection"])

    def test_unfinished_native_scoped_source_stays_unknown_without_fabricated_fields(self):
        for explicit_quantity in (False, True):
            with self.subTest(explicit_quantity=explicit_quantity):
                case = incomplete_case()
                row = case["result"]["positions"][0]
                if explicit_quantity:
                    row["proposed_quantity"] = None
                    seal(case)
                before = deepcopy(case)
                current = self.current(case)
                self.assertEqual(case, before)
                self.assertEqual(current["report_source_lineage"]["member_analysis"], case["result"])
                self.assertIsNone(row["proposed_amount"])
                self.assertEqual("proposed_quantity" in row, explicit_quantity)
                self.assertNotIn("result_digest", row["owner_scoped_financial_result"])
                self.assertNotIn("same_run_gap_price", row)
                self.assertEqual(current["report_scope"], "SOURCE_REVIEW")
                self.assertIsNone(current["current_total_twd"])
                projection = current["report_source_lineage"]["section_projection"]
                self.assertNotIn("scoped_zero_display", projection)
                self.assertEqual(projection["scoped_incomplete_display"]["decisions"], {row["symbol"]: "SOURCE_INCOMPLETE"})
                text = "\n".join(c["heading"] + c["body"] for c in current["verified_sections"]["actions"])
                self.assertIn("新增金額與股數未知", text)
                self.assertIn("未知不代表零，不構成金融或交易決策", text)
                self.assertNotIn("同輪具來源零額", text)
                incoming = self.inputs(case)["engine"]["report_sources"]["sections"]["valuation"]["payload"]
                self.assertIn("新增金額與股數未知", incoming[0]["body"])
                self.assertNotIn("零額裁定", incoming[0]["body"])

    def test_unfinished_source_resealed_foreign_binding_still_rejected(self):
        for key in ("client_id", "run_id", "evaluation_at", "source_db_sha256", "asset_id"):
            with self.subTest(key=key):
                case = incomplete_case()
                case["result"]["positions"][0]["owner_scoped_financial_result"][key] = "FOREIGN"
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_unfinished_source_requires_original_rule_attempt_and_account(self):
        for attack in ("rule", "owner", "attempt", "duplicate", "status", "target", "account", "snapshot"):
            with self.subTest(attack=attack):
                case = incomplete_case(); row = case["result"]["positions"][0]
                scoped = row["owner_scoped_financial_result"]; attempt = row["financial_source_attempt"]
                if attack == "rule": scoped["owner_rule"]["run_id"] = "FOREIGN"
                elif attack == "owner": scoped["owner"]["account"] = "FOREIGN"
                elif attack == "attempt": row.pop("financial_source_attempt")
                elif attack == "duplicate": attempt["owner_scoped_financial_result"] = {}
                elif attack == "status": attempt["status"] = "COMPLETE"
                elif attack == "target": attempt["target_version"] += 1
                elif attack == "account":
                    attempt["account_analysis_binding"]["approved_document_category_scope"]["original_account_row"]["account_key"] = "FOREIGN"
                else: attempt["account_analysis_binding"]["approved_document_category_scope"]["source_snapshot_digest"] = "0" * 64
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_unfinished_source_cannot_claim_zero_completion_funding_or_trades(self):
        for key, value in (("final_amount", {"amount": "0", "currency": "USD"}), ("final_quantity", "0"),
                ("known_zero_basis", "NO_POSITIVE_DEPLOYMENT_GAP"), ("test_ledger", {}), ("shared_funding", {}),
                ("full_family_native_pipeline_complete", True), ("formal_deployment_ready", True),
                ("trade_action", "BUY"), ("production", "READY"), ("missing_inputs", []),
                ("missing_inputs", [{"field": ""}]), ("status", "UNRECOGNIZED")):
            with self.subTest(key=key, value=value):
                case = incomplete_case(); case["result"]["positions"][0]["owner_scoped_financial_result"][key] = value
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_unfinished_source_does_not_turn_proposed_amounts_into_known_zero(self):
        for amount, quantity in (({"amount": "0", "currency": "USD"}, "0"),
                ({"amount": "1", "currency": "USD"}, "1"), (None, "0"),
                ({"amount": "0", "currency": "USD"}, None), (None, False)):
            with self.subTest(amount=amount, quantity=quantity):
                case = incomplete_case(); case["result"]["positions"][0].update(proposed_amount=amount, proposed_quantity=quantity)
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_unfinished_source_cannot_grant_buy_permission_or_rebind_native_currency(self):
        for attack in ("buy_permission", "buy_permission_zero", "buy_permission_string", "currency", "pause", "qualified_pack"):
            with self.subTest(attack=attack):
                case = incomplete_case(); row = case["result"]["positions"][0]
                if attack.startswith("buy_permission"):
                    row["formal_conclusion"]["buy_permission"]["value"] = {
                        "buy_permission": True, "buy_permission_zero": 0, "buy_permission_string": "FALSE"}[attack]
                elif attack == "currency":
                    scoped = row["owner_scoped_financial_result"]
                    scoped["owner"]["currency"] = "TWD"
                    scoped["owner_rule"]["owner"]["currency"] = "TWD"
                    account = row["financial_source_attempt"]["account_analysis_binding"]
                    account["owner"]["currency"] = "TWD"
                    account["approved_document_category_scope"]["owner"]["currency"] = "TWD"
                elif attack == "pause": row["normal_buy_pause"] = {}
                else: row["financial_source_attempt"]["qualified_financial_pack"] = True
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_unfinished_plan_must_have_no_execution_amount_quantity_or_intent(self):
        case = incomplete_case(); scoped = case["result"]["positions"][0]["owner_scoped_financial_result"]
        scoped["execution_plan"] = {"execution_amount": None, "execution_quantity": None,
            "order_plan": {"should_place_order": False, "order_intent_id": None, "quantity": None}}
        seal(case)
        self.current(case)
        for location, key, value in (("execution_plan", "execution_amount", "0"),
                ("execution_plan", "execution_quantity", "0"), ("order_plan", "should_place_order", True),
                ("order_plan", "order_intent_id", "INVENTED"), ("order_plan", "quantity", "1")):
            with self.subTest(location=location, key=key):
                attacked = deepcopy(case)
                plan = attacked["result"]["positions"][0]["owner_scoped_financial_result"]["execution_plan"]
                (plan if location == "execution_plan" else plan["order_plan"])[key] = value
                seal(attacked)
                with self.assertRaises(ValueError): self.inputs(attacked)

    def test_unfinished_optional_scoped_digest_and_original_digests_are_checked(self):
        for field in ("scoped", "row", "report"):
            with self.subTest(field=field):
                case = incomplete_case(); row = case["result"]["positions"][0]
                if field == "scoped":
                    row["owner_scoped_financial_result"]["result_digest"] = "0" * 64
                    F.member_refresh(case)
                elif field == "row": row["result_digest"] = "0" * 64
                else: case["result"]["report_digest"] = "0" * 64
                with self.assertRaises(ValueError): self.inputs(case)

    def test_arbitrary_zero_positive_negative_boolean_or_incomplete_values_rejected(self):
        for amount, quantity in [(0, "0"), ({"amount": "1", "currency": "USD"}, "0"),
            ({"amount": "-1", "currency": "USD"}, "0"), ({"amount": False, "currency": "USD"}, "0"),
            ({"amount": "NaN", "currency": "USD"}, "0"), ({"amount": "0", "currency": "USD"}, None),
            (None, "0"), ({"amount": "0", "currency": "USD"}, False)]:
            with self.subTest(amount=amount, quantity=quantity):
                case = F.member_case(); case["result"]["positions"][0].update(
                    proposed_amount=amount, proposed_quantity=quantity)
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_scoped_rehashed_wrong_client_run_DB_time_or_asset_rejected(self):
        for key in ("client_id", "run_id", "source_db_sha256", "evaluation_at", "asset_id"):
            with self.subTest(key=key):
                case = zero_case("scoped")
                case["result"]["positions"][0]["owner_scoped_financial_result"][key] = "FOREIGN"
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_scoped_account_and_original_row_cannot_be_rebound(self):
        case = zero_case("scoped"); row = case["result"]["positions"][0]
        row["financial_source_attempt"]["account_analysis_binding"]["approved_document_category_scope"]["original_account_row"]["account_key"] = "FOREIGN"
        seal(case)
        with self.assertRaisesRegex(ValueError, "W6_MEMBER_ZERO_ACCOUNT_BINDING"): self.inputs(case)

    def test_missing_disagreeing_source_or_quote_receipts_rejected(self):
        for attack in ("missing", "duplicate", "quote", "rule", "conclusion"):
            with self.subTest(attack=attack):
                case = zero_case("scoped"); row = case["result"]["positions"][0]
                if attack == "missing": row.pop("financial_source_attempt")
                elif attack == "duplicate":
                    row["financial_source_attempt"]["owner_scoped_financial_result"] = {}
                elif attack == "quote": row["owner_scoped_financial_result"]["canonical_quote_proof"]["position"]["owner"]["account"] = "FOREIGN"
                elif attack == "rule": row["owner_scoped_financial_result"]["owner_rule"]["owner"]["account"] = "FOREIGN"
                else: row["formal_conclusion"]["conclusion_digest"] = "0" * 64
                if attack != "conclusion": seal(case)
                else: F.member_refresh(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_market_or_target_versions_cannot_disagree_with_zero_source(self):
        for field in ("market_currency", "market_sha", "target_version", "source_target_version"):
            case = zero_case("scoped"); row = case["result"]["positions"][0]
            if field == "market_currency": row["market"]["market_identity"]["currency"] = "TWD"
            elif field == "market_sha": row["market"]["source_sha256"] = "0" * 64
            elif field == "target_version": row["financial_source_attempt"]["target_version"] += 1
            else: row["financial_source_attempt"]["same_run_source_binding"]["target_version"] += 1
            seal(case)
            with self.subTest(field=field), self.assertRaises(ValueError): self.inputs(case)

    def test_scoped_resealed_execution_cycle_and_raw_value_contradictions_rejected(self):
        attacks = [lambda f: f["final_amount"].update(amount="1"),
            lambda f: f.update(final_quantity="1"), lambda f: f["position_gap"].update(positive_deployment_gap="1"),
            lambda f: f["execution_plan"]["order_plan"].update(should_place_order=True),
            lambda f: f["execution_plan"].update(execution_quantity="1"),
            lambda f: f["test_ledger"].update(new_cycles=1), lambda f: f["test_ledger"].update(new_intents=1),
            lambda f: f.update(formal_deployment_ready=True), lambda f: f.update(trade_action="BUY")]
        for index, change in enumerate(attacks):
            with self.subTest(index=index):
                case = zero_case("scoped"); change(case["result"]["positions"][0]["owner_scoped_financial_result"]); seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_pause_wrong_run_time_symbol_currency_price_or_votes_rejected(self):
        for field in ("run_id", "evaluation_at", "symbol", "source_sha256", "position_valuation_source_sha256", "session"):
            with self.subTest(field=field):
                case = zero_case("pause"); case["result"]["positions"][0]["normal_buy_pause"][field] = "FOREIGN"; seal(case)
                with self.assertRaises(ValueError): self.inputs(case)
        for attack in ("currency", "vote", "down", "sell", "amount"):
            with self.subTest(attack=attack):
                case = zero_case("pause"); row = case["result"]["positions"][0]
                if attack == "currency": row["normal_buy_pause"]["amount"]["currency"] = "TWD"
                elif attack == "vote": row["normal_buy_pause"]["votes"]["down_accel"] = ["INVENTED"]
                elif attack == "down": row["core_observation"]["result"]["technical"]["runaway_down"] = "FALSE"
                elif attack == "sell": row["normal_buy_pause"]["sell_intent_created"] = True
                else: row["normal_buy_pause"]["amount"]["amount"] = "1"
                seal(case)
                with self.assertRaises(ValueError): self.inputs(case)

    def test_original_row_and_report_digests_still_reject_tampering(self):
        for field in ("row", "report"):
            case = zero_case("pause")
            if field == "row": case["result"]["positions"][0]["result_digest"] = "0" * 64
            else: case["result"]["report_digest"] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError): self.inputs(case)

    def test_report_and_row_buy_sell_permissions_remain_denied(self):
        for location in ("result", "row"):
            for key, value in (("trade_action", "BUY"), ("trade_action", "SELL"),
                               ("trade_authorization", "BROKER"), ("full_native_pipeline_complete", True)):
                case = zero_case("pause")
                target = case["result"] if location == "result" else case["result"]["positions"][0]
                target[key] = value; seal(case)
                with self.subTest(location=location, key=key, value=value), self.assertRaises(ValueError): self.inputs(case)

    def test_from_menu04_pins_both_original_objects_and_copies_them(self):
        case = zero_case("scoped"); receipt = {k: case[k] for k in ("request", "result")}
        producer = W6.MemberAnalysisReportProducer.from_menu04(receipt, source_id="SYNTHETIC_ZERO_SOURCE",
            rules_sha="e" * 64, expected_request_digest=F.A.digest(receipt["request"]),
            expected_result_digest=F.A.digest(receipt["result"]))
        receipt["result"]["positions"].clear()
        self.assertEqual(len(producer(case["source"], {})["engine"]["report_sources"]["result"]["positions"]), 3)
        with self.assertRaisesRegex(ValueError, "W6_MENU04_RECEIPT_DIGEST_MISMATCH"):
            W6.MemberAnalysisReportProducer.from_menu04(receipt, source_id="SYNTHETIC_ZERO_SOURCE",
                rules_sha="e" * 64, expected_request_digest="0" * 64, expected_result_digest="0" * 64)

    def test_macro_quarter_is_lossless_and_checker_is_not_globally_changed(self):
        case = zero_case("pause")
        case["result"]["positions"][0]["macro_observations"] = {"observed": {"gdp": {"as_of": "2026-Q3"}}}
        seal(case)
        module = F.A._runtime("report_financial_sections", "W8")
        strict_time = module._time
        current = self.current(case)
        self.assertIs(module._time, strict_time)
        self.assertEqual(current["report_source_lineage"]["member_analysis"], case["result"])
        projection = current["report_source_lineage"]["section_projection"]
        self.assertEqual(projection["observation_period_adapter"]["original_periods"][0]["value"], "2026-Q3")
        self.assertFalse(projection["observation_period_adapter"]["release_time_invented"])

    def test_future_quarter_and_invalid_market_or_publication_dates_still_rejected(self):
        for field, value in (("as_of", "2027-Q1"), ("as_of", "2026-Q5"), ("available_at", "2026-Q3")):
            case = zero_case("pause")
            case["result"]["positions"][0]["macro_observations"] = {"gdp": {"as_of": "2026-Q3", field: value}}
            seal(case)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): self.current(case)
        case = zero_case("pause")
        row = case["result"]["positions"][0]
        row["macro_observations"] = {"gdp": {"as_of": "2026-Q3"}}
        row["market"]["as_of"] = "2026-Q3"; seal(case)
        with self.assertRaises(ValueError): self.current(case)

    def test_missing_bond_market_is_not_zero_or_rewritten_source(self):
        case = F.member_financial_case()
        coverage = case["result"]["all_asset_coverage"]
        bond = coverage["bonds"][0]; bond["market"] = None
        bond["result_digest"] = F.A.digest({k: v for k, v in bond.items() if k != "result_digest"})
        coverage["coverage_digest"] = F.A.digest({k: v for k, v in coverage.items() if k != "coverage_digest"})
        seal(case); before = deepcopy(case)
        current = self.current(case)
        self.assertEqual(case, before)
        self.assertEqual(current["report_source_lineage"]["member_analysis"], case["result"])
        self.assertEqual(current["asset_coverage_summary"]["coverage_digest"], coverage["coverage_digest"])
        cards = current["verified_sections"]["bond"]
        card = next(c for c in cards if c["heading"].startswith(bond["symbol"]))
        self.assertIn("原收盤價：UNKNOWN", card["body"])
        self.assertEqual(card["source_result_sha256"], F.A.digest(case["result"]))


if __name__ == "__main__":
    unittest.main()
