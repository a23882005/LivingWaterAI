"""Read an optional structured, sourced ChatGPT macro snapshot.

Only PUBLIC macro data is allowed. All values are individually range-checked,
date-checked, and source-checked before being admitted as fallbacks.
"""
import datetime as dt
import json
import math
from pathlib import Path
from urllib.parse import urlparse

# key: (minimum, maximum, maximum observation age in calendar days)
BOUNDS = {
    "fed_current": (0, 20, 16),
    "fed_target": (0, 20, 16),
    "pmi": (15, 85, 55),
    "cpi": (-1, 15, 55),
    "mmfi": (0, 100, 5),
    "vix": (5, 120, 5),
    "dxy": (65, 160, 5),
    "oil": (0, 250, 5),
    "yield_10y": (0, 20, 10),
    "yield_curve": (-6, 6, 10),
    "hy": (0, 30, 10),
    "real_y_fred": (-6, 12, 10),
    "pe": (1, 120, 35),
    "pe_qqq": (1, 180, 35),
    "pe_vt": (1, 120, 35),
    "fear": (0, 100, 5),
}
MAX_SNAPSHOT_HOURS = 50

def read_verified_fallback(path: Path, now=None):
    if not path.is_file():
        return {}, [f"no ChatGPT snapshot at {path.name}"]
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        asof = dt.datetime.fromisoformat(doc["as_of"].replace("Z", "+00:00"))
        if asof.tzinfo is None:
            raise ValueError("as_of must include timezone")
        age = (now - asof).total_seconds() / 3600
        if not 0 <= age <= MAX_SNAPSHOT_HOURS:
            raise ValueError(f"snapshot too old/future: {age:.1f}h")
        metrics = doc["metrics"]
        if not isinstance(metrics, dict):
            raise ValueError("metrics must be a JSON object")
    except (OSError, ValueError, KeyError, TypeError) as e:
        return {}, [f"invalid ChatGPT snapshot: {e}"]
    good = {}
    notes = []
    today = now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
    for key, row in metrics.items():
        if key not in BOUNDS:
            notes.append(f"{key}: unknown key")
            continue
        try:
            if not isinstance(row, dict):
                raise ValueError("record must be object")
            value = float(row["value"])
            lo, hi, max_age = BOUNDS[key]
            if not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError("numeric out of range")
            published = dt.date.fromisoformat(row["data_date"])
            days = (today-published).days
            if not 0 <= days <= max_age:
                raise ValueError(f"stale/future observation ({days} days)")
            source = str(row["source"]).strip()
            url = str(row["url"]).strip()
            parsed = urlparse(url)
            if (not source or len(source) < 3 or parsed.scheme != "https"
                    or not parsed.hostname or parsed.hostname in ("localhost", "127.0.0.1")):
                raise ValueError("missing valid HTTPS source")
            good[key] = {"value": value, "data_date": str(published),
                         "source": source, "url": url}
        except (ValueError, TypeError, KeyError) as e:
            notes.append(f"{key}: rejected ({e})")
    return good, notes

def make_manual_input(fallback, override=""):
    """Feed the owner's existing Selenium/manual fields without prompting."""
    if override:
        obj=json.loads(override)
        return {k: float(obj[k]) for k in ("fed_current","fed_target","pmi","cpi")} | {
            "mmfi": float(obj["mmfi"]) if obj.get("mmfi") is not None else None,
        }
    return {key: fallback[key]["value"] if key in fallback else None
            for key in ("fed_current","fed_target","pmi","cpi","mmfi")}
