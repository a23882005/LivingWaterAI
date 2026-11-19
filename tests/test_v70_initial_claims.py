"""Regression checks for the V70 initial claims source."""

from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from scripts import v70_initial_claims as claims


FRONT_PAGE = """8:30 A.M. (Eastern) Thursday, January 08, 2026
UNEMPLOYMENT INSURANCE WEEKLY CLAIMS
SEASONALLY ADJUSTED DATA

In the week ending January 3, the advance figure for seasonally adjusted initial claims was 208,000,
an increase of 8,000 from the previous week's revised level. The previous week's level was revised
up by 1,000 from 199,000 to 200,000. The 4-week moving average was 211,750, a decrease of 7,250
from the previous week's unrevised average of 219,000.

The advance seasonally adjusted insured unemployment rate was 1.2 percent.
"""
TABLE_PAGE = """UNEMPLOYMENT INSURANCE DATA FOR REGULAR STATE PROGRAMS
WEEK ENDING                  January 3  December 27   Change  December 20  Prior Year
Initial Claims (SA)            208,000      200,000   +8,000      215,000     207,000
Initial Claims (NSA)           300,860      271,183  +29,677      282,000     306,657
4-Wk Moving Average (SA)       211,750      219,000   -7,250      218,000     214,500

WEEK ENDING                  December 27  December 20   Change  December 13  Prior Year
Insured Unemployment (SA)      1,914,000    1,858,000  +56,000     1,892,000   1,900,000
4-Wk Moving Average (SA)       1,892,750    1,879,750  +13,000     1,885,000   1,900,000
"""
AS_OF = datetime.fromisoformat("2026-01-08T13:31:00+00:00")


class InitialClaimsTests(unittest.TestCase):
    def read(self, front=FRONT_PAGE, table=TABLE_PAGE, as_of=AS_OF):
        pages = [Mock(extract_text=Mock(return_value=text)) for text in (front, table)]
        with patch.object(claims, "PdfReader", return_value=Mock(pages=pages)):
            return claims.parse_release(b"%PDF-test", as_of)

    def test_selects_initial_claims_and_distinguishes_initial_from_revised(self):
        data = self.read()
        self.assertEqual(data["observation_week_ending"], "2026-01-03")
        self.assertEqual(data["previous_week_ending"], "2025-12-27")
        self.assertEqual(data["initial_claims_advance"], 208000)
        self.assertEqual(data["previous_initial_claims_in_release"], 200000)
        self.assertEqual(data["previous_initial_claims_original"], 199000)
        self.assertEqual(data["week_over_week_change"], 8000)
        self.assertEqual(data["four_week_average_advance"], 211750)
        self.assertEqual(data["previous_four_week_average_original"], 219000)

    def test_refuses_mismatched_values_and_prior_dates(self):
        with self.assertRaisesRegex(ValueError, "disagree on seasonally adjusted values"):
            self.read(front=FRONT_PAGE.replace("208,000", "210,000"))
        with self.assertRaisesRegex(ValueError, "disagree on the observation weeks"):
            self.read(table=TABLE_PAGE.replace("December 27", "December 20", 1))

    def test_refuses_releases_before_their_publication_time(self):
        before_publication = datetime.fromisoformat("2026-01-08T13:29:00+00:00")
        with self.assertRaisesRegex(ValueError, "later than the requested as-of timestamp"):
            self.read(as_of=before_publication)

    def test_refuses_a_conflicting_revision(self):
        with self.assertRaisesRegex(ValueError, "prior-week level revision"):
            self.read(front=FRONT_PAGE.replace("up by 1,000", "up by 2,000"))

    def test_older_pdf_cannot_replace_newer_snapshot(self):
        record = self.read()
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "claims.json"
            claims.write_snapshot(target, record)
            original = target.read_bytes()
            self.assertEqual(json.loads(original), record)
            with self.assertRaisesRegex(ValueError, "newer release"):
                claims.write_snapshot(target, record | {"published_at": "2025-12-31T08:30:00-05:00"})
            self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
