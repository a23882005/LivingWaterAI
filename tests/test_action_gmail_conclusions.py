"""Verify actual email subjects/bodies without connecting to Gmail."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

SOURCE = Path(__file__).resolve().parents[1] / "scripts/send_action_gmail_report.py"
spec = importlib.util.spec_from_file_location("gmail_report", SOURCE)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ConclusionTests(unittest.TestCase):
    def render_email(self, conclusion, branch="family/example"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact.mkdir()
            env = {
                "SOURCE_RUN_NAME": "LivingWaterAI 11h Verified V70.3 Site Deploy",
                "SOURCE_RUN_ID": "test-run",
                "SOURCE_RUN_CREATED_AT": "2026-10-30T02:18:06Z",
                "SOURCE_RUN_UPDATED_AT": "2026-10-30T02:18:07Z",
                "SOURCE_RUN_EVENT": "push",
                "SOURCE_RUN_HEAD_BRANCH": branch,
                "GMAIL_APP_PASSWORD": "test-only",
                "GITHUB_STEP_SUMMARY": str(root / "summary.md"),
            }
            if conclusion is not None:
                env["SOURCE_RUN_CONCLUSION"] = conclusion
            smtp = MagicMock()
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", ["report", "--artifact-dir", str(artifact)]), patch.object(report.smtplib, "SMTP_SSL", return_value=smtp), patch("builtins.print"):
                    report.main()
                message = smtp.__enter__.return_value.send_message.call_args.args[0]
                body = message.get_body(preferencelist=("plain",)).get_content()
                self.assertIn(body.strip(), (root / "summary.md").read_text())
                return str(message["Subject"]), body
            finally:
                os.chdir(old_cwd)

    def test_all_conclusions(self):
        cases = [("success", "成功摘要"), ("failure", "失敗警報"),
                 ("timed_out", "逾時警報"), ("skipped", "略過通知"),
                 ("cancelled", "取消通知"), ("neutral", "中性結果通知"),
                 ("action_required", "需要處理"), ("stale", "執行狀態過期"),
                 ("unexpected", "狀態待確認"), (None, "狀態待確認"),
                 ("", "狀態待確認")]
        for conclusion, label in cases:
            with self.subTest(conclusion=conclusion):
                subject, body = self.render_email(conclusion)
                self.assertIn(label, subject)
                self.assertIn("2026/10/30", subject)
                if conclusion != "failure":
                    self.assertNotIn("失敗警報", subject)
                if conclusion != "success":
                    self.assertNotIn("全步驟成功", body)
                    self.assertNotIn("實際資料與答案", body)
                if conclusion not in {"failure", "timed_out"}:
                    self.assertNotIn("修復方向", body)

    def test_skipped_development_branch_explains_guard(self):
        _, body = self.render_email("skipped")
        self.assertIn("符合部署保護條件", body)
        self.assertIn("family/example", body)
        self.assertNotIn("未取得 QA.json", body)

    def test_skipped_main_does_not_guess_branch_reason(self):
        _, body = self.render_email("skipped", "main")
        self.assertNotIn("符合部署保護條件", body)

    def test_failure_keeps_diagnostics(self):
        _, body = self.render_email("failure")
        self.assertIn("未取得 QA.json", body)
        self.assertIn("修復方向", body)


if __name__ == "__main__":
    unittest.main()
