"""Minimal dependency-free XLSX reader used by C Work2.

Scope is intentionally narrow: values, sheet names, headers, cached formula values,
and Excel-style dates. It does not calculate formulas and it never mutates source files.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Tuple

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# Excel built-in formats that represent dates/times.
BUILTIN_DATE_FMT_IDS = {
    14, 15, 16, 17, 18, 19, 20, 21, 22,
    27, 28, 29, 30, 31, 32, 33, 34, 35, 36,
    45, 46, 47,
    50, 51, 52, 53, 54, 55, 56, 57, 58,
}

_CELL_RE = re.compile(r"([A-Z]+)([0-9]+)$")


@dataclass(frozen=True)
class SheetData:
    name: str
    headers: List[str]
    rows: List[Dict[str, Any]]
    max_row: int
    max_col: int


@dataclass(frozen=True)
class WorkbookData:
    sheets: Dict[str, SheetData]
    date1904: bool
    formula_cell_count: int


def _col_to_idx(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _strip_numfmt_literals(code: str) -> str:
    code = re.sub(r'"[^"]*"', '', code)
    code = re.sub(r"\\.", '', code)
    code = re.sub(r"\[[^\]]*\]", '', code)
    code = re.sub(r"_.", '', code)
    code = re.sub(r"\*.", '', code)
    return code.lower()


def _looks_like_date_format(code: str) -> bool:
    c = _strip_numfmt_literals(code)
    # Requiring y or d avoids misclassifying ordinary formats containing only m.
    return bool(re.search(r"[yd]", c)) or bool(re.search(r"h+.*s+|s+.*h+", c))


def _excel_serial_to_value(value: float, date1904: bool, has_time: bool) -> Any:
    epoch = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    dt = epoch + timedelta(days=value)
    if has_time or value % 1:
        return dt.replace(microsecond=0)
    return dt.date()


def _load_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out: List[str] = []
    for si in root.findall(f"{NS}si"):
        out.append("".join((t.text or "") for t in si.iter(f"{NS}t")))
    return out


def _load_style_date_map(zf: zipfile.ZipFile) -> Dict[int, Tuple[bool, bool]]:
    """Return style index -> (is_date, has_time)."""
    try:
        root = ET.fromstring(zf.read("xl/styles.xml"))
    except KeyError:
        return {}

    custom: Dict[int, str] = {}
    num_fmts = root.find(f"{NS}numFmts")
    if num_fmts is not None:
        for n in num_fmts.findall(f"{NS}numFmt"):
            try:
                custom[int(n.attrib["numFmtId"])] = n.attrib.get("formatCode", "")
            except (KeyError, ValueError):
                continue

    out: Dict[int, Tuple[bool, bool]] = {}
    cell_xfs = root.find(f"{NS}cellXfs")
    if cell_xfs is None:
        return out
    for idx, xf in enumerate(cell_xfs.findall(f"{NS}xf")):
        try:
            fmt_id = int(xf.attrib.get("numFmtId", "0"))
        except ValueError:
            fmt_id = 0
        code = custom.get(fmt_id, "")
        is_date = fmt_id in BUILTIN_DATE_FMT_IDS or (bool(code) and _looks_like_date_format(code))
        stripped = _strip_numfmt_literals(code)
        has_time = fmt_id in {18, 19, 20, 21, 22, 45, 46, 47} or bool(re.search(r"[hs]", stripped))
        out[idx] = (is_date, has_time)
    return out


def _sheet_targets(zf: zipfile.ZipFile) -> Tuple[List[Tuple[str, str]], bool]:
    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    wbpr = wb_root.find(f"{NS}workbookPr")
    date1904 = bool(wbpr is not None and wbpr.attrib.get("date1904") in {"1", "true", "True"})

    rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rels = {
        r.attrib["Id"]: r.attrib["Target"]
        for r in rel_root.findall(f"{PKG_REL_NS}Relationship")
    }
    sheets_node = wb_root.find(f"{NS}sheets")
    if sheets_node is None:
        return [], date1904
    out: List[Tuple[str, str]] = []
    for s in sheets_node.findall(f"{NS}sheet"):
        name = s.attrib.get("name", "")
        rid = s.attrib.get(f"{REL_NS}id")
        target = rels.get(rid or "")
        if not target:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = "xl/" + target.lstrip("/")
        path = str(Path(path)).replace("\\", "/")
        out.append((name, path))
    return out, date1904


def _cell_value(cell: ET.Element, shared: List[str], style_map: Dict[int, Tuple[bool, bool]], date1904: bool) -> Any:
    t = cell.attrib.get("t")
    style_idx = int(cell.attrib.get("s", "0") or 0)
    v = cell.find(f"{NS}v")

    if t == "inlineStr":
        is_node = cell.find(f"{NS}is")
        if is_node is None:
            return ""
        return "".join((x.text or "") for x in is_node.iter(f"{NS}t"))
    if v is None or v.text is None:
        return None
    raw = v.text
    if t == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return raw
    if t in {"str", "e"}:
        return raw
    if t == "b":
        return raw == "1"

    try:
        num = float(raw)
    except ValueError:
        return raw

    is_date, has_time = style_map.get(style_idx, (False, False))
    if is_date:
        return _excel_serial_to_value(num, date1904, has_time)
    if num.is_integer():
        return int(num)
    return num


def read_xlsx(path: str | Path) -> WorkbookData:
    path = Path(path)
    with zipfile.ZipFile(path, "r") as zf:
        shared = _load_shared_strings(zf)
        style_map = _load_style_date_map(zf)
        targets, date1904 = _sheet_targets(zf)
        sheets: Dict[str, SheetData] = {}
        formula_count = 0

        for sheet_name, sheet_path in targets:
            root = ET.fromstring(zf.read(sheet_path))
            grid: Dict[Tuple[int, int], Any] = {}
            max_row = 0
            max_col = 0
            for c in root.iter(f"{NS}c"):
                ref = c.attrib.get("r", "")
                m = _CELL_RE.match(ref)
                if not m:
                    continue
                col_idx = _col_to_idx(m.group(1))
                row_idx = int(m.group(2)) - 1
                max_row = max(max_row, row_idx + 1)
                max_col = max(max_col, col_idx + 1)
                if c.find(f"{NS}f") is not None:
                    formula_count += 1
                grid[(row_idx, col_idx)] = _cell_value(c, shared, style_map, date1904)

            headers = [str(grid.get((0, c), "") or "").strip() for c in range(max_col)] if max_row else []
            rows: List[Dict[str, Any]] = []
            for r in range(1, max_row):
                vals = [grid.get((r, c)) for c in range(max_col)]
                if all(v is None or v == "" for v in vals):
                    continue
                row = {headers[c]: vals[c] for c in range(max_col) if headers[c]}
                rows.append(row)
            sheets[sheet_name] = SheetData(sheet_name, headers, rows, max_row, max_col)

    return WorkbookData(sheets=sheets, date1904=date1904, formula_cell_count=formula_count)


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value
