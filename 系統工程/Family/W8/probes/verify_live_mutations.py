"""Execute existing B06 transactions on bytes from all four real formal DBs.

Remote Drive access is GET only. Transactions run against private in-memory
working copies and validate the actual SQLite constraints without any changes
to live customer accounts. Logs contain no sensitive client data.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
base=Path(__file__).resolve().parents[2]
for p in (base/"W7",base/"W8",base/"W7"/"deployment"):
    sys.path.insert(0,str(p))
from drive_service_transport import GoogleDriveTransport
from deployment.provision_private_runtime import CONFIG_ID, PRIVATE_PARENT, private_meta
from official_family_entry import RESOURCE_BY_ACCOUNT
from official_mutations import make_writer
from 資料存取管理 import transaction,checked

def main():
    d=GoogleDriveTransport(*(os.environ[k] for k in
        ("FAMILY_DRIVE_CLIENT_ID","FAMILY_DRIVE_CLIENT_SECRET","FAMILY_DRIVE_REFRESH_TOKEN")))
    api="https://www.googleapis.com/drive/v3/files/"
    private_meta(d,CONFIG_ID,PRIVATE_PARENT)
    cfg=json.loads(d.call(api+CONFIG_ID+"?alt=media",raw=True))
    checks=0
    stage="INIT"
    for account,resource in RESOURCE_BY_ACCOUNT.items():
        fid=cfg["headers"][resource]["file_id"]
        original=d.call(api+fid+"?alt=media",raw=True)
        original_sha=hashlib.sha256(original).hexdigest()
        import sqlite3,tempfile
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"before.db"
            path.write_bytes(original)
            with sqlite3.connect(path) as db:
                client=db.execute("select client_id from family_member_identity").fetchone()[0]
            stamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            onboarding={
                "interview_confirmed":True,"as_of_utc":stamp,
                "confirmation_reference":"W8_SCHEMA_QA_LOCAL_COPY_ONLY",
                "request_id":"W8QA_"+account,"account_key":"W8QA",
                "mentor_answers":{"phase":"verified real DB schema QA"},
                "holdings":[{"ticker":"W8QA","currency":"TWD",
                             "exchange":"UNKNOWN","display_name":"Schema only",
                             "confirmed_quantity":"1","reported_market_value":"1"}],
                "cash":[{"currency":"TWD","reported_amount":"0"}]}
            versions=[
                ("first_allocation",{"client_id":client,"record":onboarding}),
                ("adjust_target",{"client_id":client,"record":{
                    "confirmed":True,"source_reference":"W8_SCHEMA_QA_LOCAL_COPY_ONLY",
                    "allocations":[{"instrument_key": "USER01-"+hashlib.sha256(
                        (client+":W8QA:UNKNOWN:TWD").encode()).hexdigest()[:24],
                        "weight":"1.000000"}]}}),
                ("new_funding",{"client_id":client,"record":{
                    "source_id":"W8_QA_FUND","source_reference":"W8_SCHEMA_QA_LOCAL_COPY_ONLY",
                    "account_key":"W8QA","currency":"TWD","amount":"100",
                    "as_of_utc":stamp}}),
                ("update_profile",{"client_id":client,"record":{
                    "field_key":"funding_goal","value":"owner verified in real use",
                    "source_reference":"W8_SCHEMA_QA_LOCAL_COPY_ONLY"}}),
                ("record_event",{"client_id":client,"record":{
                    "event_id":"W8_QA_EVENT","event_kind":"TEST_ONLY_COPIED_DB",
                    "source_reference":"W8_SCHEMA_QA_LOCAL_COPY_ONLY",
                    "event_occurred_at_utc":stamp,
                    "account_key":"W8QA",
                    "changes":[{"entity_kind":"OTHER","field_name":"record",
                                "after_value":"schema verified"}]}})
            ]
            working=original
            for idx,(operation,payload) in enumerate(versions):
                global STAGE
                STAGE=operation
                working,result,duplicate=transaction(
                    working,"account:"+account,
                    "schema-test-%s-%s"%(account,idx),operation,payload,
                    make_writer(operation,client))
                assert not duplicate and result["status"]=="STORED"
                checked(working)
                checks+=1
        remote_after=d.call(api+fid+"?alt=media",raw=True)
        assert hashlib.sha256(remote_after).hexdigest()==original_sha
    assert checks==20
    print(json.dumps({"status":"PASS","real_db_schemas":4,
                      "schema_bound_transactions":checks,
                      "live_db_writes":0,"remote_unchanged":4,
                      "transaction_commit_integrity":"PASS"}))

if __name__=="__main__":
    try:main()
    except Exception as exc:
        # SQLite constraint diagnostics contain schema and column names only.
        # Never print DB contents, identifiers, account values or owner holdings.
        code = getattr(exc, "sqlite_errorname", None)
        print(json.dumps({"status":"FAIL","type":type(exc).__name__,
                          "sqlite_code":code,"stage":globals().get("STAGE","unknown"),
                          "live_db_writes":0}))
        raise SystemExit(1)
