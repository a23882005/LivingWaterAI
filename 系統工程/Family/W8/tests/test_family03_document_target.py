"""Cover the read-only document fallback and separate same-ticker target roles."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from approved_target_input import build_approved_target_view
from family03_target import approved_framework, account_preview, confirmed_request


class DocumentPreviewTest(unittest.TestCase):
    def setUp(self):
        private = TemporaryDirectory()
        self.addCleanup(private.cleanup)
        folder = Path(private.name)
        doc = folder / "approved.md"
        mapping = folder / "mapping.json"
        rows = [("FUND", "FUND", "股票ETF", 70), ("SHORT_BOND", "SHORT", "債券ETF", 15),
                ("SHORT_RESERVE", "SHORT", "cash", 10), ("TWD_CASH", "TWD_CASH", "cash", 5)]
        lines = [f"| {role} | {w}% |" for role, _, _, w in rows]
        doc.write_text("\n".join(lines))
        self.client = "fam_" + "a"*32
        config = dict(client_id=self.client, target_version=1, allocation_version="QA",
                      source_reference="private-test", source_available_at="2026-01-01T00:00:00Z",
                      sha256=sha256(doc.read_bytes()).hexdigest(),
                      rows=[dict(source_line=line, weight=str(w/100))
                            for line, (_, _, _, w) in zip(lines, rows)],
                      mappings=[dict(instrument_id=i,ticker=t,asset_type=a) for i,t,a,_ in rows])
        mapping.write_text(json.dumps(dict(client_id=self.client,document_target=config)))
        self.source = dict(document_path=doc,mapping_path=mapping,
                           mapping_sha256=sha256(mapping.read_bytes()).hexdigest())

    def load(self):
        return approved_framework(self.source, self.client, build_approved_target_view)

    def test_replay_and_roles(self):
        snapshot = {"tables":{"final_target_version":[]}, "source_sha256":"db"}
        p = account_preview(snapshot, {"方案":"測試"}, {"NEW":100}, {}, None, "rev", self.load)
        self.assertEqual(p["每百萬單位"], {"NEW":700000, "SHORT_BOND":150000,
                                       "SHORT_RESERVE":100000, "TWD_CASH":50000})
        self.assertEqual(p["角色對照"]["TWD_CASH"],dict(instrument_id="CASH_TWD",ticker=None,currency="TWD"))
        self.assertNotEqual(p["revision"], "rev")
        positions = [dict(instrument_id=i,ticker=t,base_currency=ccy,
                          weight=dict(value_state="KNOWN",value=w))
                     for i,t,ccy,w in [("NEW","NEW","USD",.7), ("SHORT_BOND","SHORT","USD",.15),
                         ("SHORT_RESERVE","SHORT","USD",.1), ("CASH_TWD",None,"TWD",.05)]]
        result = dict(work6_snapshot_id="qa-only",loop_status="FINAL_TARGET_CONFIRMED",
            identity={"client_id":self.client},route={"decision":"C_ONLY"},
            final_target_engine_result={"formal_output_eligibility":dict(eligible=True,scope="FULL")},
            final_target=dict(value_state="KNOWN",snapshot=dict(positions=positions,confirmation_status="CONFIRMED")))
        payload = dict(action="confirm_account",owner_confirmed=True,revision=p["revision"],
                       source_sha256="db",mentor_result=result)
        self.assertEqual(len(confirmed_request(p,payload,self.client)["record"]["allocations"]),4)
        positions[1]["ticker"]="DIFFERENT"
        with self.assertRaises(ValueError):
            confirmed_request(p,payload,self.client)

    def test_changed_document_mapping_or_member(self):
        with self.assertRaises(ValueError):
            approved_framework(self.source, "fam_"+"b"*32, build_approved_target_view)
        self.source["document_path"].write_text(self.source["document_path"].read_text()+"\nUpdated")
        with self.assertRaises(ValueError):
            self.load()
        self.source["mapping_sha256"]="0"*64
        with self.assertRaises(ValueError):
            self.load()
