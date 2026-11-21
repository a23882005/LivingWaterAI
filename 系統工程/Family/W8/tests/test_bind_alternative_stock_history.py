from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.bind_alternative_stock_history import bind


def test_bind_keeps_producer_approval_and_rejects_newer_or_changed_data(tmp_path):
    source = tmp_path / "history"
    source.mkdir()
    csv = source / "TEST.csv"
    csv.write_text("Date,Open,High,Low,Close,Volume\n2026-11-18,1,1,1,1,1\n")
    item = {"status": "OK", "file_name": csv.name, "formal_deployment_eligible": False,
            "last_verified_utc": "2026-11-19T01:00:00Z", "latest_observation": "2026-11-18",
            "sha256": sha256(csv.read_bytes()).hexdigest()}
    manifest = source / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "Family.W8.AlternativeMarketHistory.v1",
                                   "items": {"TEST": item}}))
    manifest_hash = sha256(manifest.read_bytes()).hexdigest()
    data = {"schema_version": "Family.W8.MemberFinancialProducer.v1", "client_id": "member",
            "source_db_sha256": "db", "asset_id": "TEST", "target_version": 2,
            "configuration": {"request_seed": {"trade_authorization": "NONE"}}}
    producer = tmp_path / "original.json"
    producer.write_text(json.dumps(data))
    pin = {"local_path": str(producer), "sha256": sha256(producer.read_bytes()).hexdigest()}
    config = {"client_id": "member", "source_db_sha256": "db",
              "run_binding": {"evaluation_at": "2026-11-19T00:00:00Z"},
              "financial_producer_sources": {"TEST": pin, "OTHER": {"untouched": True}}}
    destination = tmp_path / "bound"
    with pytest.raises(PermissionError, match="SCOPE_OR_CUTOFF:TEST"):
        bind(config, source, manifest_hash, ["TEST"], destination)
    assert not destination.exists()

    config["run_binding"]["evaluation_at"] = "2026-11-19T02:00:00Z"
    result = bind(config, source, manifest_hash, ["TEST"], destination)
    assert result["financial_producer_sources"]["OTHER"] == {"untouched": True}
    assert config["financial_producer_sources"]["TEST"] == pin
    raw = Path(result["financial_producer_sources"]["TEST"]["local_path"]).read_bytes()
    assert sha256(raw).hexdigest() == result["financial_producer_sources"]["TEST"]["sha256"]
    data["configuration"]["alternative_source_dir"] = str(source)
    assert json.loads(raw) == data

    csv.write_text("changed")
    with pytest.raises(PermissionError, match="CSV_BYTES_CHANGED:TEST"):
        bind(config, source, manifest_hash, ["TEST"], destination)
