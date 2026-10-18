# 最後修改日期時間：2026/10/18 17:10（台灣時間）｜檔案名稱：test_v703_failure_mail.py｜版本：Gmail 失敗通知測試
"""Offline Gmail failure-notification acceptance test; SMTP is mocked."""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("mail_report",ROOT/"scripts/send_action_gmail_report.py")
mail_report=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mail_report)


class GmailFailureNotificationTests(unittest.TestCase):
    def test_failure_reports_actual_qa_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            (root/"artifact").mkdir()
            (root/"artifact"/"QA.json").write_text(json.dumps({
                "requiredScoringValidated":16,"missing":[],
                "problems":["m04: monthly data stale", "m05: monthly data stale"]},ensure_ascii=False),encoding="utf8")
            env={"SOURCE_RUN_NAME":"LivingWaterAI 11h Verified V70.3 Site Deploy",
                 "SOURCE_RUN_ID":"12345", "SOURCE_RUN_CONCLUSION":"failure",
                 "SOURCE_RUN_URL":"https://github.com/a23882005/LivingWaterAI/actions/runs/12345",
                 "SOURCE_RUN_CREATED_AT":"2026-10-18T03:20:00Z",
                 "SOURCE_RUN_UPDATED_AT":"2026-10-18T03:21:00Z",
                 "GMAIL_APP_PASSWORD":"dummy"}
            old=os.getcwd()
            try:
                os.chdir(td)
                with patch.dict(os.environ,env), patch.object(sys,"argv",["send_action_gmail_report.py","--artifact-dir","artifact"]),patch.object(mail_report.smtplib,"SMTP_SSL") as smtp:
                    mail_report.main()
                    smtp.return_value.__enter__.return_value.login.assert_called_once()
                    sent=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
                body=sent.get_body(preferencelist=("plain",)).get_content()
                self.assertIn("16/22",body)
                self.assertIn("m04: monthly data stale",body)
                self.assertIn("失敗",str(sent["Subject"]))
                self.assertNotIn("本次 Workflow 全步驟成功",body)
                self.assertEqual(len(list(sent.iter_attachments())),1)
            finally:
                os.chdir(old)


if __name__=="__main__":
    unittest.main()
