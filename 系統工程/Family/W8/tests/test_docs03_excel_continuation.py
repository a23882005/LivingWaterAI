"""Verify Menu 03 writes and resumes real synthetic workbooks."""
from hashlib import sha256
import json
import os
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from openpyxl import Workbook, load_workbook

from test_docs03_writeback import READBACK_CASES, TestLogin, docs03, incomplete_download_bytes, mutation_fixture


calc = docs03._load_module("equity_sleeve")
guide = docs03._load_module("family03_guide")
plans = docs03._load_module("family03_plans")


class ExcelContinuationTests(unittest.TestCase):
    def test_write_route_only_accepts_existing_answer_forms(self):
        answer = {"revision": "revision", "question_id": "question", "key": "goal", "reply": "choice"}
        for extra in ({"edit": "sector"}, {"edit": ""}, {"edit": None},
                      {"action": "history"}, {"action": "start_plans", "edit": "goal"},
                      {"workbook_id": "elsewhere"}):
            with self.subTest(extra=extra):
                self.assertFalse(docs03._is_progress_write(answer | extra))

    def test_original_answer_continuation_matrix(self):
        operations = ("answer", "edit legacy", "start plans", "restore")
        cases = ("normal", "delayed readback", "changed workbook", "backup mismatch", "later answer present")
        for combined in (False, True):
            for operation in operations:
                for case in cases:
                    with self.subTest(combined=combined, operation=operation, case=case), TemporaryDirectory() as folder:
                        root = Path(folder)
                        # Use the supported Python writer fallback for repeatable workbook I/O in the matrix.
                        with patch.dict(os.environ, {"CODEX_PRIMARY_RUNTIME_NODE_MODULES": str(root / "no-node-package")}):
                            self.check_turn(root, combined, operation, case)

    def test_progress_candidate_recovery_matrix(self):
        cases = ("candidate lost", "candidate changed", "candidate empty",
                 "candidate changed after send", "candidate lost after save")
        for operation in ("answer", "restore"):
            for combined in (False, True):
                for case in cases:
                    with self.subTest(operation=operation, combined=combined, case=case), TemporaryDirectory() as folder:
                        root = Path(folder)
                        with patch.dict(os.environ, {"CODEX_PRIMARY_RUNTIME_NODE_MODULES": str(root / "no-node-package")}):
                            self.check_turn(root, combined, operation, case)

    def test_progress_incomplete_download_recovers_original_event_matrix(self):
        for operation in ("answer", "restore"):
            for combined in (False, True):
                for case in READBACK_CASES:
                    with self.subTest(operation=operation, combined=combined, case=case), TemporaryDirectory() as folder:
                        root = Path(folder)
                        with patch.dict(os.environ, {"CODEX_PRIMARY_RUNTIME_NODE_MODULES": str(root / "no-node-package")}):
                            self.check_turn(root, combined, operation, case)

    def check_turn(self, root, combined, operation, case):
        member = "mou"
        source = root / f"{member}_03_股票配置選擇進度.xlsx"
        backup = root / "backup.xlsx"
        auth = TestLogin()
        book = Workbook()
        main = book.active
        main.title = "選擇進度"
        main.append(["股票配置・選擇進度", member])
        main.append(["目前進度", "已作答"])
        main.append(["續選位置", "原題"])
        book.create_sheet("標的及比例")["A1"] = "股票桶內配置"
        history = book.create_sheet("選擇歷程")
        history.append(["事件識別", "台灣時間", "家人", "題目代碼", "當時問題",
                        "當時選項", "系統建議與結果", "本人選擇", "當時提供的影片",
                        "選擇狀態", "作答後有效答案", "方案識別"])
        old_event = "a" * 64
        if operation != "answer":
            state = {"goal": guide.QUESTIONS["goal"][1][0]}
            previous_key = "goal"
            if operation == "edit legacy":
                state["sector"] = guide.QUESTIONS["sector"][1][0]
                previous_key = "sector"
            elif operation == "restore":
                state = plans.initial([])
                state["plans"][0]["layers"]["主軸"] = {"VT": 100}
                state["plans"][0]["targets"] = {"主軸": 100, "衛星": 0, "繁星": 0}
                previous_key = "save"
            history.append([old_event, "2026-11-20T10:00:00+08:00", member, previous_key,
                            "", "[]", "{}", "", "", "本人暫選", json.dumps(state), ""])
        book.save(source)
        original_count = history.max_row - 1
        original_bytes = source.read_bytes()
        original_revision = sha256(original_bytes).hexdigest()
        copyfile(source, backup)

        pool = Workbook()
        pool.remove(pool.active)
        for role, symbol in zip(plans.ROLES, ("VT", "XLF", "ZTS")):
            sheet = pool.create_sheet(role)
            sheet.append(["代碼", "名稱或投資範圍", "來源", "理由", "注意", "比較", "網址"])
            sheet.append([symbol, "fixture", "test", "test", "test", "", "test"])
        pool.save(root / plans.POOL_NAME)
        book.save(root / "標的績效基準資料.xlsx")
        entry = SimpleNamespace(current_snapshot=lambda: {"source_sha256": "fixture-ledger"})
        holdings = lambda _: {"ledger_only_positions": [], "analysis_security_positions": []}
        handler = plans.menu_handler(entry, member, root, calc, guide, holdings, progress_path=source)
        if operation == "restore":
            payload = {"action": "restore", "version": old_event, "slot": "方案二", "revision": original_revision}
            expected_key, position = "restore", "檢視完整方案"
        else:
            options = {"edit legacy": {"edit": "goal"}, "start plans": {"action": "start_plans"}}
            args = options.get(operation, {})
            prompt = handler(args)
            choice = prompt["選項"][1 if operation == "edit legacy" else 0]
            self.assertEqual(prompt.get("作答入口", {}), args)
            payload = {**prompt.get("作答入口", {}),
                       **{k: prompt[k] for k in ("key", "revision", "question_id")}, "reply": choice}
            expected_key = prompt["key"]
            position = guide.QUESTIONS["returns"][0] if operation == "edit legacy" else "投資目標"

        download = Mock(return_value=("progress-id", source))
        menu = mutation_fixture.MENU.FamilyMenu(
            SimpleNamespace(require_login=auth.require_login, family_login=auth),
            project_name="MOU", login_account="MOU", handlers={"adjust_target": handler})
        build_menu = Mock(return_value=menu)
        args = dict(auth=auth, document_id="fixture-doc",
                    document={"documentId": "fixture-doc", "revisionId": "fixture-revision"},
                    project_id="fixture-project", conversation_id="original-chat", workspace_dir=root,
                    login_account="MOU", client_id=auth.client_id, family_alias=member,
                    progress_file_id="progress-id", download_progress=download)
        download_ledger = Mock(return_value=("ledger-id", root / "synthetic-ledger.db"))

        def turn(message, data=None, verified_backup=None):
            if combined:
                return docs03.run_project_docs03_native_turn(
                    **args, project_name="MOU", official_drive_file_id="ledger-id",
                    download_original=download_ledger, build_original_menu=build_menu, mutation_staging_dir=root,
                    message_id=message, payload=data, verified_progress_backup=verified_backup)
            return docs03.run_project_docs03_progress(
                **args, build_menu=build_menu, message_id=message, payload=data, verified_backup=verified_backup)

        first = turn("answer", payload)
        self.assertEqual(first["status"], "DOCS03_BACKUP_REQUIRED")
        self.assertEqual(source.read_bytes(), original_bytes)
        journal, _ = docs03._journal_directory(
            root, args["project_id"] + "|03-progress", args["conversation_id"], create=False)
        candidate = next(journal.glob("upload-*.xlsx"))
        if case == "changed workbook":
            main["B3"] = "另一筆變更"
            book.save(source)
        elif case == "backup mismatch":
            bad = root / "bad-backup.xlsx"
            main["B3"] = "備份內容不同"
            book.save(bad)
            with self.assertRaisesRegex(ValueError, "FAMILY03_PROGRESS_BACKUP_MISMATCH"):
                turn("bad-backup", verified_backup=("bad-id", bad))
        elif case == "candidate lost":
            candidate.unlink()
        elif case == "candidate changed":
            with candidate.open("ab") as artifact:
                artifact.write(b"altered candidate bytes")
        elif case == "candidate empty":
            candidate.write_bytes(b"")

        incomplete = root / "partial-download" / source.name
        if case in READBACK_CASES:
            incomplete.parent.mkdir()
        if case == "readback preflight":
            incomplete.write_bytes(incomplete_download_bytes(source.read_bytes(), case))
            download.side_effect = [("progress-id", source), ("progress-id", incomplete)]
            retry = turn("partial-preflight", verified_backup=("backup-id", backup))
            self.assertEqual(retry["status"], "DOCS03_READ_RETRY_REQUIRED")
            self.assertNotIn("update_file_args", retry)
            download.side_effect = None

        update = turn("backup", verified_backup=("backup-id", backup))
        if case in ("changed workbook", "candidate lost", "candidate changed", "candidate empty"):
            self.assertEqual(update["status"], "DOCS03_PREVIEW_STALE")
            self.assertNotIn("update_file_args", update)
            self.assertEqual(len(plans.read_progress(source, member, calc.reader_module())[1]), original_count)
            if case.startswith("candidate"):
                self.assertEqual(source.read_bytes(), original_bytes)
                self.assertEqual(turn("continue-stale"), update)
                self.assertEqual(turn("fresh-answer", payload)["status"], "DOCS03_BACKUP_REQUIRED")
            return
        self.assertEqual(update["status"], "DOCS03_DRIVE_UPDATE_REQUIRED")
        self.assertEqual(update["update_file_args"]["fileId"], "progress-id")
        if case == "delayed readback":
            pending = turn("wait", verified_backup=("backup-id", backup))
            self.assertEqual(pending["status"], "AWAIT_DRIVE_CONFIRMATION")
            self.assertNotIn("update_file_args", pending)
        if case == "candidate changed after send":
            good_copy = root / "uploaded-by-connector.xlsx"
            copyfile(candidate, good_copy)
            candidate.write_bytes(b"changed after send")
            pending = turn("candidate-no-longer-needed", verified_backup=("backup-id", backup))
            self.assertEqual(pending["status"], "AWAIT_DRIVE_CONFIRMATION")
            self.assertNotIn("update_file_args", pending)
            copyfile(good_copy, source)
        else:
            copyfile(update["update_file_args"]["file_uri"], source)
        if case == "candidate lost after save":
            candidate.unlink()
        if case == "later answer present":
            later = load_workbook(source)
            later["選擇歷程"].append(["b" * 64, "2026-11-20T11:00:00+08:00", member])
            later["選擇進度"]["B3"] = "更新後的題目"
            later.save(source)
            later.close()
        if case in READBACK_CASES:
            incomplete.write_bytes(incomplete_download_bytes(source.read_bytes(), case))
            download.return_value = ("progress-id", incomplete)
            messages = ("partial", "partial-again") if case == "readback repeated" else ("partial",)
            for message in messages:
                retry = turn(message, verified_backup=("backup-id", backup))
                self.assertEqual(retry["status"], "DOCS03_READ_RETRY_REQUIRED")
                self.assertNotIn("update_file_args", retry)
            download.return_value = ("progress-id", source)
        receipt = turn("continue")
        self.assertEqual(receipt["status"], "PERSISTED_REMOTE_VERIFIED")
        observed = receipt["result"]["progress_receipt"]
        self.assertEqual(observed["事件識別"], first["request_id"])
        self.assertEqual(observed["事件序號"], original_count + 1)
        self.assertEqual(observed["讀回時為最新作答"], case != "later answer present")
        self.assertEqual(observed["讀回時續選位置"], "更新後的題目" if case == "later answer present" else position)
        self.assertEqual(turn("resend", payload), receipt)
        if case in READBACK_CASES:
            self.assertEqual(turn("partial"), receipt)
        self.assertEqual(turn("again"), receipt)
        _, rows = plans.read_progress(source, member, calc.reader_module())
        self.assertEqual(len(rows), original_count + 1 + (case == "later answer present"))
        event = rows[original_count]
        self.assertEqual(event["題目代碼"], expected_key)
        self.assertEqual(sum(row["事件識別"] == observed["事件識別"] for row in rows), 1)
        if operation == "edit legacy":
            self.assertEqual(json.loads(event["作答後有效答案"]),
                             {"goal": payload["reply"], "sector": guide.QUESTIONS["sector"][1][0]})
        elif operation == "restore":
            restored = json.loads(event["作答後有效答案"])
            self.assertEqual(restored["slot"], 1)
            self.assertEqual(restored["plans"][0], restored["plans"][1])
        if case != "later answer present" and operation != "restore":
            next_prompt = handler({})
            self.assertEqual(next_prompt["key"], "returns" if operation == "edit legacy" else "goal")
        self.assertEqual(backup.read_bytes(), original_bytes)
        build_menu.assert_called_once()
        self.assertEqual(download_ledger.call_count, int(combined))
