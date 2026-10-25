"""Verify official Drive report folders without changing member databases."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode

BASE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BASE/"W7"))
sys.path.insert(0,str(BASE/"W8"))
from drive_service_transport import GoogleDriveTransport
from private_family_service import REPORT_FOLDERS, REPORT_PREFIXES

def main():
    d=GoogleDriveTransport(*(os.environ[k] for k in
        ("FAMILY_DRIVE_CLIENT_ID","FAMILY_DRIVE_CLIENT_SECRET","FAMILY_DRIVE_REFRESH_TOKEN")))
    api="https://www.googleapis.com/drive/v3/files?"
    counts={}
    for account,name in REPORT_FOLDERS.items():
        q="name = '"+name+"' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        data=d.call(api+urlencode({"q":q,"fields":"nextPageToken,files(id,name,mimeType)",
                                   "pageSize":100}))
        found=data.get("files",[])
        assert not data.get("nextPageToken") and len(found)==1
        folder=found[0]["id"]
        q="'"+folder+"' in parents and trashed = false"
        contents=d.call(api+urlencode({"q":q,
            "fields":"nextPageToken,files(id,name,mimeType)","pageSize":100}))
        assert not contents.get("nextPageToken")
        reports=[row for row in contents.get("files",[])
            if row.get("name","").startswith(REPORT_PREFIXES[account])
            and row.get("mimeType") in ("text/html","application/pdf")]
        counts[account]=len(reports)
    assert len(counts)==4
    print(json.dumps({"status":"PASS","official_report_folders":4,
                      "read_only":True,"member_db_writes":0,
                      "report_count_total":sum(counts.values())}))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print(json.dumps({"status":"FAIL","error_type":type(e).__name__}))
        raise SystemExit(1)
