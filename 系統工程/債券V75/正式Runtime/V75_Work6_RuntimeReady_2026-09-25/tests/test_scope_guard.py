from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "v75_runtime"
WORK3 = RUNTIME / "work3.py"
WORK3_MODELS = RUNTIME / "work3_models.py"


def test_work6_isolated_to_work6_modules():
    for path in RUNTIME.glob("*.py"):
        if path.name in {"work6.py", "work6_models.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "WORK6_ENGINE_VERSION" not in text
        assert "WORK6_CONTRACT_ID" not in text
        assert "Work6RuntimeReadySnapshot" not in text


def test_work6_does_not_implement_external_production_side_effects():
    text = (RUNTIME / "work6.py").read_text(encoding="utf-8").lower()
    for forbidden in ("requests.", "httpx.", "subprocess", "socket", "broker_api", "place_order", "execute_order"):
        assert forbidden not in text


def test_work3_does_not_execute_deployment_mapping_or_predicates():
    text = WORK3.read_text(encoding="utf-8")
    assert "DEPLOYMENT_PCT_CONTRACT" not in text
    assert "GLOBAL_EVALUATION_PRECEDENCE" not in text
    assert "predicate_results" not in text


def test_work3_models_do_not_add_later_work_decision_fields():
    text = WORK3_MODELS.read_text(encoding="utf-8")
    for forbidden in (
        "deployment_state", "deployment_pct", "deploy_amount", "new_money_action",
        "existing_position_action", "existing_reduction_pct", "classification",
    ):
        assert forbidden not in text


def test_work3_never_calculates_later_work_sgov_undeployed_contribution():
    text = WORK3.read_text(encoding="utf-8").lower()
    assert "v75_undeployed_to_sgov" not in text
