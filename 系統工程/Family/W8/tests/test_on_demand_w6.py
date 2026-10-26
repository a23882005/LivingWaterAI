"""W8 13 approved W6 render adapter. Synthetic only, no personal DB."""
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("test_w8_w6_data_fixture",HERE/"test_w6_current_data.py")
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
spec=importlib.util.spec_from_file_location("w8_approved_w6_adapter",HERE.parent/"on_demand_w6.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

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
