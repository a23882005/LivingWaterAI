# 最後修改日期時間（台灣時間）：2026/10/16 09:07｜版本：V70-3-12 Gmail 通知 v1.4｜檔案名稱：send_action_gmail_report.py
"""Email successful LivingWaterAI Action run results and attach its actual data artifact."""
import argparse
import csv
import json
import os
import smtplib
import zipfile
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

def fmt(value):
    if value is None or value == "":
        return "NA"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)

def macro_lines(data, label):
    items = data.get("items") or data.get("indicators") or {}
    if not isinstance(items, dict):
        return [f"{label}：找不到可解析的指標清單。"]
    counts = {}
    lines = [f"{label}實際指標：{len(items)} 項"]
    for key, row in items.items():
        if not isinstance(row, dict):
            lines.append(f"- {key}: {fmt(row)}")
            continue
        status = row.get("status", "未標示")
        counts[status] = counts.get(status, 0) + 1
        value = row.get("value", row.get("raw_value"))
        date = row.get("observation_date", row.get("dataDate", "日期未提供"))
        source = row.get("source_url", row.get("source", "來源未提供"))
        lines.append(f"- {key}: {fmt(value)} | 日期 {date} | 狀態 {status} | 來源 {source}")
    lines.insert(1, "狀態統計：" + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "無"))
    return lines

def history_lines(root, region):
    manifests = list(root.rglob("manifest.json"))
    report = next((load_json(p) for p in manifests if load_json(p)), None)
    if not report:
        return [f"{region}歷史資料：artifact 中未找到 manifest.json。"]
    items = report.get("items", {})
    counts = {}
    lines = [f"{region}歷史資料：{len(items)} 個標的；來源 {report.get('data_source','未標示')}；更新時間 UTC {report.get('generated_utc','未標示')}"]
    for symbol, row in items.items():
        status = row.get("status", "未標示")
        counts[status] = counts.get(status, 0) + 1
        csv_path = next((p for p in root.rglob(symbol.replace("/", "_") + ".csv")), None)
        close = "NA"
        if csv_path:
            try:
                with csv_path.open(newline="", encoding="utf-8-sig") as f:
                    records = list(csv.DictReader(f))
                if records:
                    last = records[-1]
                    date = last.get("Date") or last.get("date") or row.get("latest_observation", "日期未標示")
                    close = last.get("Close", "NA")
                else:
                    date = row.get("latest_observation", "日期未標示")
            except (OSError, csv.Error):
                date = row.get("latest_observation", "日期未標示")
        else:
            date = row.get("latest_observation", "日期未標示")
        lines.append(f"- {symbol}: {status} | 最新觀測 {date} | 收盤 {close} | 歷史筆數 {row.get('rows','NA')}")
    lines.insert(1, "狀態統計：" + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "無"))
    return lines

def make_summary(root, name):
    files = list(root.rglob("*.json"))
    for p in files:
        data = load_json(p)
        if not isinstance(data, dict):
            continue
        if "18_macro_verification.json" in p.name:
            return macro_lines(data, "總經爬蟲18項")
        if "V70_macro_latest.json" in p.name:
            verification = data.get("verification", {})
            lines = [f"網站建置資料：schema={data.get('schema','未標示')}；asOf={data.get('asOf','未標示')}",
                     f"品質閘門：ready={verification.get('ready')}；獨立指標={verification.get('independentIndicators')}；傳輸欄={len(data.get('indicators',{}))}"]
            lines.extend(macro_lines({"indicators": data.get("indicators", {})}, "部署資料"))
            return lines
    if "IB global" in name:
        return history_lines(root, "全球 IB watchlist")
    if "IB Taiwan" in name:
        return history_lines(root, "台灣 IB watchlist")
    if files:
        return [f"artifact JSON 數量：{len(files)}"] + [str(p.relative_to(root)) for p in files]
    return ["成功的 Action 未提供可解析的 JSON 報告；請查看原始執行紀錄。"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args()
    root = Path(args.artifact_dir)
    run_name = os.environ.get("SOURCE_RUN_NAME", "LivingWaterAI GitHub Actions")
    run_id = os.environ.get("SOURCE_RUN_ID", "unknown")
    run_url = os.environ.get("SOURCE_RUN_URL", "")
    conclusion = os.environ.get("SOURCE_RUN_CONCLUSION", "success")
    created = os.environ.get("SOURCE_RUN_CREATED_AT", "")
    updated = os.environ.get("SOURCE_RUN_UPDATED_AT", "")
    def taipei_stamp(value):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y/%m/%d %H:%M:%S")
        except (ValueError, TypeError):
            return "未提供"
    start_time = taipei_stamp(created)
    end_time = taipei_stamp(updated)
    lines = [
        "LivingWaterAI GitHub Actions 實際執行摘要",
        f"任務：{run_name}",
        f"執行結果：{conclusion}",
        f"開始時間（台灣）：{start_time}",
        f"完成時間（台灣）：{end_time}",
        f"Run ID：{run_id}",
        f"執行紀錄：{run_url or '未提供'}",
    ]
    if "11h Verified V70.3 Site Deploy" in run_name:
        lines.append("部署與網站讀回：本次 Workflow 全步驟成功，包含 Hostinger 首頁與 JSON 線上驗證。")
    lines.extend(["", "實際資料與答案：", *make_summary(root, run_name), "",
                  "附件為該次 GitHub Actions 上傳的原始資料 artifact 壓縮檔；內容以本次實際執行輸出為準。"])
    report_text = "\n".join(lines)
    print(report_text)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary_file:
            summary_file.write("# LivingWaterAI 實際執行報告\n\n" + report_text + "\n")
    msg = EmailMessage()
    msg["From"] = "a23882005@gmail.com"
    msg["To"] = "a23882005@gmail.com"
    msg["Subject"] = f"[LivingWaterAI] {start_time[:10]} {run_name} 執行摘要"
    msg.set_content("\n".join(lines))
    archive = Path("action-result-artifact.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in root.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(root))
    if archive.stat().st_size <= 24 * 1024 * 1024:
        msg.add_attachment(archive.read_bytes(), maintype="application", subtype="zip", filename=f"LivingWaterAI-{run_id}-artifact.zip")
    else:
        msg.add_attachment("\n".join(lines).encode("utf-8"), maintype="text", subtype="plain", filename=f"LivingWaterAI-{run_id}-summary.txt")
        raise RuntimeError("Action artifact exceeds Gmail attachment limit; refusing to claim full data was emailed.")
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not password:
        raise RuntimeError("GitHub Actions secret GMAIL_APP_PASSWORD is missing.")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login("a23882005@gmail.com", password)
        smtp.send_message(msg)
    print(f"GMAIL_REPORT_SENT run_id={run_id} to=a23882005@gmail.com attachment_bytes={archive.stat().st_size}")

if __name__ == "__main__":
    main()
