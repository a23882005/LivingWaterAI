"""Different snapshot comparison: official NOW screenshot is NOT settlement parity."""
import datetime as dt
import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("m06_math",ROOT/"scripts/probe_m06_fedwatch_free.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class OfficialScreenshotReference(unittest.TestCase):
    def test_now_screenshot_arithmetic_and_different_snapshot(self):
        # User-supplied 2026-10-14 CME FedWatch NOW snapshot, not 2026-10-13 settlement.
        ps=[0.5,6.1,21.2,32.5,25.6,11.1,2.6,0.3]
        levels=[f"{3.75+0.25*i:.2f}%-{4+0.25*i:.2f}%" for i in range(8)]
        feed={"target_source":"fred","trade_date":"2026-10-14",
              "current_target":"3.75%-4.00%","meetings":[
                  {"date":"2027-10-27","probabilities":dict(zip(levels,ps))}]}
        result=mod.calculate(feed,dt.date(2026,10,14))
        self.assertAlmostEqual(result["probability_total_pct"],99.9,places=3)
        self.assertAlmostEqual(result["expected_target_mid_pct"],4.67980,places=4)
        self.assertAlmostEqual(result["m06_expected_rate_change_quarters"],3.2192,places=4)
        previous_settlement="2026-10-13"
        self.assertNotEqual(result["as_of_settlement"],previous_settlement)
        self.assertNotAlmostEqual(result["m06_expected_rate_change_quarters"],3.2783,places=3)

if __name__=="__main__":
    unittest.main()
