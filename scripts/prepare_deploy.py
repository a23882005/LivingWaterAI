#!/usr/bin/env python3
"""Validate and stage ONLY the V70.2 single-page site for Hostinger.

A deployment run uploads one file, index.html, and never removes remote files.
This keeps the existing production page intact on failed macro refreshes.
"""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "V70_Live.html"
DESTINATION = ROOT / "site_dist" / "index.html"

def prepare_index(html: str, run_id: str) -> str:
    if not re.fullmatch(r"[0-9]{1,30}", str(run_id)):
        raise ValueError("Unexpected workflow run id")
    if html.count("</html>") != 1 or html.count("</body>") != 1:
        raise ValueError("Unexpected HTML closing tags")
    if "<title>投資戰情室 V70.2" not in html or "投資戰情室 V70.2" not in html:
        raise ValueError("Wrong V70.2 template")
    if "Template Not Found." in html:
        raise ValueError("Source contains missing-template placeholder")
    if "// Zone（V70.2 四區）            const zEl" in html:
        raise ValueError("V70.2 source contains JavaScript line-comment corruption")
    marker = f"<!-- LivingWaterAI V70.2 verified deployment run={run_id} -->"
    if "<!DOCTYPE html>" not in html[:120]:
        raise ValueError("Unexpected HTML prolog")
    return html.replace("<!DOCTYPE html>", "<!DOCTYPE html>\n" + marker, 1)

def stage(run_id: str, source: Path = SOURCE, destination: Path = DESTINATION) -> Path:
    document = prepare_index(source.read_text(encoding="utf-8"), run_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return destination

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print("Staged:", stage(args.run_id))
