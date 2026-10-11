import pytest
from pydantic import ValidationError

from helpers import cloned_payload
from v75_runtime.models import BasisPointValue, Money, PercentValue, PercentagePointValue, V75RunInput


def test_valid_base_input_parses():
    model = V75RunInput.model_validate(cloned_payload())
    assert model.bond_executable_budget.amount == 1000


def test_percent_is_0_to_100_not_fraction_contract():
    assert PercentValue(value=25, unit="PERCENT").value == 25
    with pytest.raises(ValidationError):
        PercentValue(value=101, unit="PERCENT")


def test_pct_pp_bps_units_do_not_cross_map():
    with pytest.raises(ValidationError):
        PercentValue(value=25, unit="BASIS_POINT")
    with pytest.raises(ValidationError):
        PercentagePointValue(value=1, unit="PERCENT")
    with pytest.raises(ValidationError):
        BasisPointValue(value=25, unit="PERCENTAGE_POINT")


def test_money_requires_nonnegative_and_iso_style_currency():
    assert Money(amount="1.25", currency="usd").currency == "USD"
    with pytest.raises(ValidationError):
        Money(amount="-1", currency="USD")
    with pytest.raises(ValidationError):
        Money(amount="1", currency="US")


def test_run_currency_mismatch_fails():
    payload = cloned_payload()
    payload["bond_executable_budget"]["currency"] = "TWD"
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(payload)


def test_future_snapshot_timestamp_fails():
    payload = cloned_payload()
    payload["market_snapshot"]["data_timestamp"] = "2026-09-25T09:00:00+08:00"
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(payload)
