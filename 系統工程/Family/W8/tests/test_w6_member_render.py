"""Source-neutral W6 v16 member renderer regressions (no customer data)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import unittest

PATH=Path(__file__).resolve().parents[1]/"w6_member_render.py"
SPEC=importlib.util.spec_from_file_location("w8_report_member_renderer",PATH)
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def official_radar():
    return {"source_reference":"synthetic-approved-scores",
            "data_provenance":"SOURCE_BACKED",
            "views":{key:{"levels":[1,2,3,4,5,6]} for key in (
                "current_defense","current_attack","target_defense","target_attack")}}


class RendererGates(unittest.TestCase):
    def test_bad_w6_archive_never_renders(self):
        with TemporaryDirectory() as d:
            f=Path(d)/"bad.zip"
            f.write_bytes(b"not the accepted W6 package")
            with self.assertRaisesRegex(ValueError,"W6_APPROVED_V16_ZIP_SHA_MISMATCH"):
                M._extract_approved(f)

    def test_complete_four_radar(self):
        page=M._radar_panels(official_radar())
        self.assertEqual(page.count("<svg"),4)
        self.assertIn("目標攻擊",page)

    def test_missing_radar_rejected(self):
        obj=official_radar()
        del obj["views"]["target_attack"]
        with self.assertRaisesRegex(ValueError,"W6_FOUR_RADAR_INCOMPLETE"):
            M._radar_panels(obj)

    def test_radar_out_of_bounds_rejected(self):
        obj=official_radar()
        obj["views"]["current_attack"]["levels"][2]=7
        with self.assertRaisesRegex(ValueError,"W6_RADAR_SCORES_INVALID"):
            M._radar_panels(obj)

    def test_sections_require_all_eight_domains_and_citations(self):
        valid={key:[{"heading":"測試","body":"合成","source_reference":"unit"}]
               for key in set(M.CONTENTS.values())}
        self.assertEqual(M._verified_sections({"verified_sections":valid}),valid)
        del valid["bond"]
        with self.assertRaisesRegex(ValueError,"W6_VERIFIED_CHAPTER_CONTENT_MISSING"):
            M._verified_sections({"verified_sections":valid})

    def test_actual_pie_never_uses_wrong_weights(self):
        with self.assertRaisesRegex(ValueError,"W6_PIE_WEIGHT"):
            M._pie([{"權重":"1.25"}])

    def test_no_html_markup_from_client(self):
        self.assertEqual(M._safe("<b>"),"&lt;b&gt;")

    def test_w6_reader_title_not_fixed_to_joseph(self):
        self.assertIn("{{CLIENT_NAME}}",M._reader.__code__.co_consts or ())

if __name__=="__main__":unittest.main()
