#!/usr/bin/env python3
# 最後修改日期時間（台灣時間）：2026/10/19 08:19｜檔案名稱：update_sp500_daily.py｜版本：FRED 價格快取增量驗證
"""Fetch and validate the FRED S&P 500 daily close cache for monthly research."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500"
FIELDS = ["date", "close", "source", "series_id", "retrieved_at_utc"]


class PriceDataError(ValueError):
    pass


def parse_fred_csv(payload: bytes, as_of: date) -> list[tuple[str, str]]:
    try:
        text = payload.decode("utf-8-sig")
        rows = csv.DictReader(text.splitlines())
    except (UnicodeError, csv.Error) as exc:
        raise PriceDataError(f"FRED CSV could not be decoded: {exc}") from exc
    if not rows.fieldnames or not {"observation_date", "SP500"}.issubset(rows.fieldnames):
        raise PriceDataError("FRED response has an unexpected schema")
    values = []
    seen = set()
    for row in rows:
        raw_date, raw_close = row.get("observation_date", "").strip(), row.get("SP500", "").strip()
        if not raw_date or raw_close in ("", "."):
            continue
        try:
            day = date.fromisoformat(raw_date)
            close = float(raw_close)
        except (ValueError, TypeError) as exc:
            raise PriceDataError(f"Invalid FRED row: {row}") from exc
        if day > as_of:
            continue
        if not math.isfinite(close) or close <= 0:
            raise PriceDataError(f"Invalid S&P 500 close on {day}: {raw_close}")
        if day in seen:
            raise PriceDataError(f"Duplicate FRED observation date: {day}")
        seen.add(day)
        values.append((day.isoformat(), f"{close:.8f}".rstrip("0").rstrip(".")))
    values.sort()
    if len(values) < 1000:
        raise PriceDataError(f"FRED response is incomplete: only {len(values)} valid daily observations")
    return values


def _read_cache(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or not {"date", "close"}.issubset(reader.fieldnames):
                raise PriceDataError("Existing S&P 500 cache has an unexpected schema")
            by_date = {}
            for row in reader:
                d, close = date.fromisoformat(row["date"]), float(row["close"])
                if not math.isfinite(close) or close <= 0 or d.isoformat() in by_date:
                    raise PriceDataError(f"Invalid or duplicate cached S&P 500 row: {row}")
                by_date[d.isoformat()] = f"{close:.8f}".rstrip("0").rstrip(".")
            return sorted(by_date.items())
    except (OSError, ValueError, TypeError) as exc:
        raise PriceDataError(f"Could not validate existing S&P 500 cache: {exc}") from exc


def _fetch(url: str = URL, opener=urllib.request.urlopen, attempts: int = 4) -> bytes:
    last_error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "LivingWaterAI-MacroResearch/1.0"})
            with opener(request, timeout=30) as response:
                if response.status != 200:
                    raise PriceDataError(f"FRED returned HTTP {response.status}")
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError, PriceDataError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 8) + random.uniform(0, 0.5))
    raise PriceDataError(f"FRED request failed after {attempts} attempts: {last_error}")


def _atomic_write(path: Path, rows: list[tuple[str, str]], retrieved_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for day, close in rows:
                writer.writerow({"date": day, "close": close, "source": URL,
                                 "series_id": "FRED:SP500", "retrieved_at_utc": retrieved_at})
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def update(path: Path, as_of: date, fetcher=_fetch) -> dict:
    try:
        fresh = parse_fred_csv(fetcher(), as_of)
        if not fresh:
            raise PriceDataError("FRED returned no eligible observations")
        cache = _read_cache(path)
        merged = dict(cache)
        merged.update(fresh)
        rows = sorted((d, v) for d, v in merged.items() if date.fromisoformat(d) <= as_of)
        latest = date.fromisoformat(rows[-1][0])
        if (as_of - latest).days > 7:
            raise PriceDataError(f"Latest verified FRED close {latest} is stale for as-of {as_of}")
        retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _atomic_write(path, rows, retrieved)
        manifest = {"schema": "V70.3/sp500-daily-cache-v1", "status": "FRESH",
                    "source": "Federal Reserve Bank of St. Louis FRED", "source_url": URL,
                    "series_id": "SP500", "measure": "daily close; price return, excludes dividends",
                    "last_observation_date": latest.isoformat(), "retrieved_at_utc": retrieved,
                    "observations": len(rows), "as_of": as_of.isoformat(), "fallback_reason": ""}
        return manifest
    except Exception as exc:
        # Keep the last validated file intact; report the retrieval failure in a sidecar.
        cache = _read_cache(path)
        if not cache:
            raise PriceDataError(f"No usable verified cache; {exc}") from exc
        latest = date.fromisoformat(cache[-1][0])
        manifest = {"schema": "V70.3/sp500-daily-cache-v1", "status": "CACHE_FALLBACK",
                    "source": "Federal Reserve Bank of St. Louis FRED", "source_url": URL,
                    "series_id": "SP500", "measure": "daily close; price return, excludes dividends",
                    "last_observation_date": latest.isoformat(), "retrieved_at_utc": "",
                    "observations": len(cache), "as_of": as_of.isoformat(),
                    "fallback_reason": str(exc)}
        return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--as-of", required=True, type=date.fromisoformat)
    args = p.parse_args(argv)
    try:
        result = update(args.output, args.as_of)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, PriceDataError) as exc:
        p.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
