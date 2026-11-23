"""Identify an explicitly sourced native cash balance in the portfolio currency."""


def is_native_cash(position, denominator_currency):
    currency = position.get("base_currency")
    return (
        isinstance(currency, str)
        and len(currency) == 3
        and currency.isascii() and currency.isalpha() and currency.isupper()
        and currency == denominator_currency
        and position.get("asset_type") in ("CASH", "現金")
        and position.get("instrument_id") == "CASH_" + currency
        and position.get("ticker") in (None, "")
        and bool(position.get("source_reference_ids"))
        and (position.get("weight") or {}).get("data_quality") in ("OK", "FALLBACK_USED")
        and (position.get("weight") or {}).get("freshness") in ("FRESH", "NOT_APPLICABLE")
        and bool((position.get("weight") or {}).get("source_reference_ids"))
    )


def cash_description(position):
    return {
        "instrument_id": position["instrument_id"],
        "ticker": None,
        "base_currency": position["base_currency"],
        "weight": position["weight"]["value"],
        "source_reference_ids": list(position["source_reference_ids"]),
    }
