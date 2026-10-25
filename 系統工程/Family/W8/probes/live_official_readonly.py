"""W8 real Drive verification of all four official DBs, strictly read-only.

Service OAuth credentials are runner secrets. This probe makes GET calls only.
It never updates/copies/backs up/changes any family database, header, or journal.
Logs report statuses and counts only; no balances, IDs, accounts, data or hashes.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "W7"))
sys.path.insert(0, str(BASE / "W7" / "deployment"))
sys.path.insert(0, str(BASE / "W5"))
sys.path.insert(0, str(BASE / "W8"))
from deployment.provision_private_runtime import CONFIG_ID, PRIVATE_PARENT, private_meta
from drive_service_transport import GoogleDriveTransport
from family_input import read_snapshot
from resource_headers import validate_policies, authorize, VerifiedPrincipal
from official_family_entry import RESOURCE_BY_ACCOUNT

API = "https://www.googleapis.com/drive/v3/files/"
PAIRS = tuple(RESOURCE_BY_ACCOUNT.items())


def main():
    # Fail immediately if a credential is absent; never print the value.
    credentials = {
        key: os.environ["FAMILY_DRIVE_" + env]
        for key, env in (
            ("client_id", "CLIENT_ID"), ("client_secret", "CLIENT_SECRET"),
            ("refresh_token", "REFRESH_TOKEN")
        )
    }
    transport = GoogleDriveTransport(**credentials)
    private_meta(transport, CONFIG_ID, PRIVATE_PARENT)
    config = json.loads(transport.call(API + CONFIG_ID + "?alt=media", raw=True))
    assert config["schema"] == "Family-B06-private-resource-config-v1"
    private_meta(transport, config["policy_id"], PRIVATE_PARENT)
    policies = validate_policies(json.loads(
        transport.call(API + config["policy_id"] + "?alt=media", raw=True)))
    identities = set()
    inspected = 0
    for account, resource_key in PAIRS:
        header = config["headers"][resource_key]
        assert header["resource_key"] == resource_key
        # Server-approved B06 ACL must grant access to the specified account.
        principal = VerifiedPrincipal("account:" + account, 4_102_444_800)
        file_id = authorize(header, policies, principal, "read", 1_800_000_000)
        record = config["resources"][file_id]
        assert record["header_template"]["file_id"] == file_id
        # Download the exact current official bytes twice: no Drive mutations.
        meta = transport.call(API + file_id + "?fields=id,parents,trashed,mimeType")
        assert meta["id"] == file_id and not meta.get("trashed")
        assert record["parent_id"] in meta.get("parents", [])
        original = transport.call(API + file_id + "?alt=media", raw=True)
        assert isinstance(original, bytes) and original.startswith(b"SQLite format 3\x00")
        sha = hashlib.sha256(original).hexdigest()
        with TemporaryDirectory(prefix="official-family-w8-read-") as directory:
            path = Path(directory) / "snapshot.db"
            path.write_bytes(original)
            con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            try:
                assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
                assert not con.execute("PRAGMA foreign_key_check").fetchall()
                ids = con.execute("SELECT client_id FROM family_member_identity").fetchall()
                assert len(ids) == 1
            finally:
                con.close()
            client_id = ids[0][0]
            assert client_id not in identities
            identities.add(client_id)
            snapshot = read_snapshot(path, expected_client_id=client_id)
            assert snapshot["source_sha256"] == sha
            assert snapshot["client_id"] == client_id
        again = transport.call(API + file_id + "?alt=media", raw=True)
        assert hashlib.sha256(again).hexdigest() == sha
        inspected += 1
    assert inspected == 4 and len(identities) == 4
    print(json.dumps({
        "status": "PASS", "source": "OFFICIAL_DRIVE_DB",
        "family_count": inspected, "read_only": True, "drive_writes": 0,
        "identity_isolation": "PASS", "sqlite_integrity": "PASS",
        "foreign_keys": "PASS", "w5_snapshot": "PASS",
        "remote_sha_readback": "PASS",
        "trade_authorization": "NONE",
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Exception messages may carry private identifiers or provider responses.
        print(json.dumps({"status": "FAIL", "stage": "OFFICIAL_READ_ONLY",
                          "error_type": type(exc).__name__, "drive_writes": 0}))
        raise SystemExit(1)
