"""W8 13 approved W6 render adapter. Synthetic only, no personal DB."""
import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timezone
from tempfile import TemporaryDirectory

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("test_w8_w6_data_fixture",HERE/"test_w6_current_data.py")
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
spec=importlib.util.spec_from_file_location("w8_approved_w6_adapter",HERE.parent/"on_demand_w6.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
spec=importlib.util.spec_from_file_location("w8_report_lookup",HERE.parent/"on_demand_report_delivery.py")
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)

def output(current, **patch):
    value={"qa_passed":True,"renderer_contract":"Family.W6.v16.parameterized",
           "client_id":current["client_id"],
           "source_db_sha256":current["source_db_sha256"],
           "source_digest":current["source_digest"],
           "w6_current_digest":current["digest"],
           "run_id":current["run_id"],"data_as_of":current["market_as_of"],
           "analysis_version":"W6-v16",
           "artifacts":{"report.pdf":b"%PDF-1.4 synthetic",
                        "index.html":b"<html>synthetic</html>"}}
    value.update(patch)
    return value


class ReportLookupTest(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.client="fam_"+"c"*32;self.parent="SYNTHETIC_PRIVATE_REPORT_FOLDER"
        rendered={"qa_passed":True,"renderer_contract":"Family.W6.v16.parameterized",
            "client_id":self.client,"run_id":"SYNTHETIC_MEMBER_RUN","data_as_of":"2026-10-30T00:00:00Z",
            "analysis_version":"SYNTHETIC","source_db_sha256":"a"*64,"source_digest":"b"*64,
            "w6_current_digest":"d"*64,"report_scope":"SOURCE_REVIEW","content_state":"UNKNOWN_NAV",
            "artifacts":{"report.pdf":b"%PDF-SYNTHETIC","index.html":b"SYNTHETIC_READER",
                         "report.html":b"SYNTHETIC_FULL_DOM","report.zip":b"SYNTHETIC_ZIP"}}
        plan=delivery.prepare_report_delivery(rendered,account="AR",client_id=self.client,
            folder_id=self.parent,output_dir=self.tmp.name,created_at=datetime(2026,10,30,tzinfo=timezone.utc))
        receipts=[];self.readbacks={};self.metadata={}
        for i,row in enumerate(plan["uploads"]):
            ident="SYNTHETIC_ARTIFACT_"+str(i)
            receipts.append({"id":ident,"name":row["name"],"success":True,"parent_id":self.parent})
            self.readbacks[ident]=Path(row["path"]).read_bytes()
            self.metadata[ident]={"id":ident,"title":row["name"],"parent_ids":[self.parent],"shared":False}
        self.manifest=delivery.prepare_verified_manifest(plan,receipts,self.readbacks)
        self.metadata["SYNTHETIC_MANIFEST"]={"id":"SYNTHETIC_MANIFEST",
            "title":self.manifest["manifest_filename"],"parent_ids":[self.parent],"shared":False}

    def lookup(self,**patch):
        options=dict(account="AR",client_id=self.client,folder_id=self.parent,
            file_metadata=self.metadata,readbacks=self.readbacks,date="2026-10-30",
            expected_run_id="SYNTHETIC_MEMBER_RUN",expected_source_db_sha256="a"*64)
        options.update(patch)
        return delivery.verify_report_lookup("SYNTHETIC_MANIFEST",self.manifest["manifest_bytes"],**options)

    def test_fresh_lookup_verifies_all_artifacts_without_claiming_financial_acceptance(self):
        result=self.lookup()
        self.assertEqual(result["status"],"REPORT_LOOKUP_REMOTE_VERIFIED")
        self.assertEqual(len(result["files"]),4)
        self.assertEqual(result["financial_acceptance"],"NOT_ASSERTED")

    def test_foreign_run_member_parent_or_shared_file_is_rejected(self):
        for patch in ({"expected_run_id":"OTHER"},{"client_id":"OTHER"},{"folder_id":"OTHER"}):
            with self.subTest(patch=patch),self.assertRaises(PermissionError):self.lookup(**patch)
        self.metadata["SYNTHETIC_ARTIFACT_0"]["shared"]=True
        with self.assertRaisesRegex(PermissionError,"REPORT_LOOKUP_PRIVATE_PARENT_MISMATCH"):self.lookup()

    def test_new_download_must_match_manifest_bytes(self):
        self.readbacks["SYNTHETIC_ARTIFACT_0"]+=b"CORRUPTED"
        with self.assertRaisesRegex(RuntimeError,"REPORT_LOOKUP_ARTIFACT_READBACK_FAILED"):self.lookup()

class W6AdapterTest(unittest.TestCase):
    def source_producer(self, source, payload):
        self.assertEqual(payload, {})
        return {"market":self.m,"engine":self.e}

    def setUp(self):
        self.s,self.m,self.e=fixture.baseline()

    def test_faithful_result_passes(self):
        wrapped=mod.OnDemandW6Renderer(self.source_producer,lambda cur:output(cur))
        r=wrapped(self.s,{})
        self.assertEqual(r["run_id"],"ok-01")
        self.assertTrue(r["qa_passed"])

    def test_wrong_rendered_source_blocked(self):
        wrapped=mod.OnDemandW6Renderer(self.source_producer,
                                      lambda cur:output(cur,w6_current_digest="old_digest"))
        with self.assertRaisesRegex(ValueError,"W6_FORMAL_OUTPUT_QA_OR_SOURCE_MISMATCH"):
            wrapped(self.s,{})

    def test_missing_pdf_blocks_publish(self):
        wrapped=mod.OnDemandW6Renderer(self.source_producer,
                                      lambda cur:output(cur,artifacts={"index.html":b"ok"}))
        with self.assertRaisesRegex(ValueError,"W6_FORMAL_ARTIFACTS_INCOMPLETE"):
            wrapped(self.s,{})

    def test_caller_cannot_override_file_id(self):
        seen=[]
        wrapped=mod.OnDemandW6Renderer(lambda s,p:seen.append(1),lambda cur:output(cur))
        with self.assertRaisesRegex(ValueError,"W6_REPORT_OPTIONS_INVALID"):
            wrapped(self.s,{"db_path":"/other_family.db"})
        self.assertEqual(seen,[])

    def test_current_unverified_cash_blocks_renderer(self):
        self.s["current_cash_by_account_currency"][0]["data_state"]="NEEDS_REVIEW"
        self.s["digest"]=fixture.M._sha({k:v for k,v in self.s.items() if k!="digest"})
        calls=[]
        wrapped=mod.OnDemandW6Renderer(self.source_producer,
                                      lambda cur:calls.append(1))
        with self.assertRaisesRegex(ValueError,"W6_LATEST_CASH_NOT_VERIFIED"):
            wrapped(self.s,{})
        self.assertEqual(calls,[])

if __name__=="__main__":unittest.main()
