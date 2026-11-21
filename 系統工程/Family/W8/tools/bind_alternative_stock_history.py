"""Prepare private Member V82 producer settings for a verified analysis cache."""
from argparse import ArgumentParser
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re


def timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("ALTERNATIVE_HISTORY_TIMEZONE_REQUIRED")
    return stamp.astimezone(timezone.utc)


def bind(config, source_dir, manifest_sha256, symbols, destination, *, resolve=Path):
    """Return a member config whose selected producers use the original cache reader."""
    source_dir = Path(source_dir).resolve(strict=True)
    raw_manifest = (source_dir / "manifest.json").read_bytes()
    if sha256(raw_manifest).hexdigest() != manifest_sha256:
        raise PermissionError("ALTERNATIVE_HISTORY_MANIFEST_BYTES_CHANGED")
    manifest = json.loads(raw_manifest)
    if manifest.get("schema_version") != "Family.W8.AlternativeMarketHistory.v1":
        raise ValueError("ALTERNATIVE_HISTORY_MANIFEST_SCHEMA")
    cutoff = timestamp(config["run_binding"]["evaluation_at"])
    sources = config["financial_producer_sources"]
    pending = {}
    for symbol in symbols:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,31}", symbol):
            raise ValueError("ALTERNATIVE_HISTORY_SYMBOL_INVALID")
        item = manifest["items"][symbol]
        filename = symbol + ".csv"
        if (item["status"] != "OK" or item["file_name"] != filename
                or item["formal_deployment_eligible"] is not False
                or timestamp(item["last_verified_utc"]) > cutoff
                or date.fromisoformat(item["latest_observation"]) >= cutoff.date()):
            raise PermissionError("ALTERNATIVE_HISTORY_ANALYSIS_SCOPE_OR_CUTOFF:" + symbol)
        csv_path = (source_dir / filename).resolve(strict=True)
        if (csv_path.parent != source_dir
                or sha256(csv_path.read_bytes()).hexdigest() != item["sha256"]):
            raise PermissionError("ALTERNATIVE_HISTORY_CSV_BYTES_CHANGED:" + symbol)

        descriptor = sources[symbol]
        raw = resolve(descriptor["local_path"]).read_bytes()
        if sha256(raw).hexdigest() != descriptor["sha256"]:
            raise PermissionError("ALTERNATIVE_HISTORY_PRODUCER_BYTES_CHANGED:" + symbol)
        producer = json.loads(raw)
        if (producer.get("schema_version") != "Family.W8.MemberFinancialProducer.v1"
                or producer.get("client_id") != config["client_id"]
                or producer.get("source_db_sha256") != config["source_db_sha256"]
                or producer.get("asset_id") != symbol):
            raise PermissionError("ALTERNATIVE_HISTORY_MEMBER_OR_SYMBOL_MISMATCH:" + symbol)
        producer["configuration"]["alternative_source_dir"] = str(source_dir)
        pending[symbol] = (json.dumps(producer, ensure_ascii=False, indent=2) + "\n").encode()

    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    result = deepcopy(config)
    for symbol, raw in pending.items():
        digest = sha256(raw).hexdigest()
        path = destination / f"producer_{symbol}_{digest}.json"
        path.write_bytes(raw)
        result["financial_producer_sources"][symbol] = {"local_path": str(path), "sha256": digest}
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("manifest_sha256")
    parser.add_argument("destination", type=Path)
    parser.add_argument("symbols", nargs="+")
    args = parser.parse_args()
    result = bind(json.loads(args.config.read_bytes()), args.source_dir,
                  args.manifest_sha256, args.symbols, args.destination)
    result_bytes = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
    path = args.destination / ("member_config_" + sha256(result_bytes).hexdigest() + ".json")
    path.write_bytes(result_bytes)
    print(path)


if __name__ == "__main__":
    main()
