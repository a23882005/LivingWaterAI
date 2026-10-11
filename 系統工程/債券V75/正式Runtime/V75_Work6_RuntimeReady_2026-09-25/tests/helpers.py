from copy import deepcopy


def known_money(amount="1000", currency="USD"):
    return {"status": "KNOWN", "value": {"amount": amount, "currency": currency}}


def unknown_money():
    return {"status": "UNKNOWN", "value": None}


def base_payload():
    return {
        "client_ref": "CLIENT-X",
        "run_id": "RUN-001",
        "analysis_timestamp": "2026-09-24T10:00:00+08:00",
        "expected_rule_version": "債券V75.md v2.7.0",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
        "deployment_parameter_version": "P0-02-FROZEN",
        "broker_account_id": "US-001",
        "broker_domain_type": "US_BROKER",
        "currency": "USD",
        "bond_executable_budget": {"amount": "1000", "currency": "USD"},
        "broker_cash_total": known_money("1200"),
        "broker_cash_available": known_money("1000"),
        "broker_cash_unsettled": known_money("200"),
        "broker_cash_reserved": known_money("0"),
        "sgov_bond_bucket_amount": known_money("300"),
        "sgov_dry_powder_bucket_amount": known_money("400"),
        "funding_settlement_status": "SETTLED",
        "life_stage_code": "ACCUMULATION",
        "strategic_bond_weight_b0": {"value": "30", "unit": "PERCENT"},
        "existing_bond_holdings": [
            {"asset_id": "SGOV", "amount": {"amount": "300", "currency": "USD"}, "broker_account_id": "US-001"}
        ],
        "target_bond_holdings": [
            {"asset_id": "SGOV", "target_amount": {"amount": "700", "currency": "USD"}, "broker_account_id": "US-001"}
        ],
        "authorized_universe": ["SGOV", "SPSB"],
        "market_snapshot": {
            "data_timestamp": "2026-09-24T09:00:00+08:00",
            "data_source": "TEST_MARKET_SOURCE",
            "freshness_state": "FRESH",
            "source_lineage": ["TEST_MARKET_SOURCE"],
            "payload": {},
        },
        "v70_snapshot": {
            "data_timestamp": "2026-09-24T09:00:00+08:00",
            "data_source": "V70_2_TEST",
            "freshness_state": "FRESH",
            "source_lineage": ["V70_2_TEST"],
            "payload": {},
        },
        "source_lineage": ["WORK1_RECHECK2"],
        "per_asset_inputs": [
            {
                "asset_id": "SPSB",
                "remaining_target_gap_amount": {"amount": "500", "currency": "USD"},
                "eligibility_state": None,
                "existing_position_amount": {"amount": "0", "currency": "USD"},
                "currency": "USD",
                "broker_account_id": "US-001",
            }
        ],
        "predicate_results": [],
    }


def cloned_payload():
    return deepcopy(base_payload())
