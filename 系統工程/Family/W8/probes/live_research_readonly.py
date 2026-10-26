"""Read four real Family DBs and fetch real current evidence for menu05."""
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
BASE=Path(__file__).resolve().parents[2]
for dirname in ("W7","W8","W5","W7/deployment"):
    sys.path.insert(0,str(BASE/dirname))
from drive_service_transport import GoogleDriveTransport
from deployment.provision_private_runtime import CONFIG_ID,PRIVATE_PARENT,private_meta
from family_input import read_snapshot
from official_family_entry import RESOURCE_BY_ACCOUNT
from official_research import research_candidates
API="https://www.googleapis.com/drive/v3/files/"

def main():
    d=GoogleDriveTransport(*(os.environ[x] for x in
        ("FAMILY_DRIVE_CLIENT_ID","FAMILY_DRIVE_CLIENT_SECRET","FAMILY_DRIVE_REFRESH_TOKEN")))
    private_meta(d,CONFIG_ID,PRIVATE_PARENT)
    cfg=json.loads(d.call(API+CONFIG_ID+"?alt=media",raw=True))
    total=0
    for account,key in RESOURCE_BY_ACCOUNT.items():
        fid=cfg["headers"][key]["file_id"]
        raw=d.call(API+fid+"?alt=media",raw=True)
        sha=hashlib.sha256(raw).hexdigest()
        with TemporaryDirectory(prefix="family-research-qa-") as directory:
            p=Path(directory)/"official-copy.db"
            p.write_bytes(raw)
            import sqlite3
            with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True) as con:
                ids=con.execute("SELECT client_id FROM family_member_identity").fetchall()
            assert len(ids)==1
            snapshot=read_snapshot(p,expected_client_id=ids[0][0])
        result=research_candidates(snapshot,theme="半導體",tickers=["SOXX"])
        assert result["source"]=="OFFICIAL_FAMILY_DB_PLUS_CURRENT_PUBLIC_RSS"
        assert result["allocation_change"] is False
        assert result["trade_authorization"]=="NONE"
        assert result["candidate_instruments"][0]["ticker"]=="SOXX"
        assert result["candidate_instruments"][0]["v82_decision"]=="NOT_EVALUATED"
        assert result["status"]=="RESEARCH_EVIDENCE"
        assert hashlib.sha256(d.call(API+fid+"?alt=media",raw=True)).hexdigest()==sha
        total+=1
    assert total==4
    print(json.dumps({"status":"PASS","four_official_dbs":total,
       "published_news_evidence":"LIVE_RSS","member_db_write_count":0,
       "client_isolation":"PASS","real_source_readback":"PASS"}))

if __name__=="__main__":
    try:main()
    except Exception as e:
        print(json.dumps({"status":"FAIL","error_type":type(e).__name__}))
        raise SystemExit(1)
