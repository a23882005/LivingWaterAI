"""Read the U.S. DOL weekly initial claims release for V70 research."""

import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from pypdf import PdfReader
from pypdf.errors import PdfReadError


SOURCE_URL = "https://www.dol.gov/ui/data.pdf"
EASTERN = ZoneInfo("America/New_York")
MAX_PDF_BYTES = 5 * 1024 * 1024
WEEK_DATE = r"[A-Za-z]+\s+\d{1,2}"
COUNT = r"\d{1,3}(?:,\d{3})+|\d+"
ROW_END = r"(?=\n\s*WEEK ENDING\b|\Z)"


def required_match(pattern, text, field, flags=0):
    match = re.search(pattern, text, flags)
    if match is None:
        raise ValueError(f"Missing DOL {field}")
    return match


def number(value):
    return int(value.replace(",", "").replace("−", "-"))


def release_time(stamp):
    match = required_match(
        r"(\d{1,2}):(\d{2})\s+([AP])\.?M\.?\s+\(Eastern\)\s+"
        r"[A-Za-z]+,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        stamp, "Eastern release timestamp", re.IGNORECASE,
    )
    hour, minute, period, day = match.groups()
    clock = time(int(hour) % 12 + (12 if period.upper() == "P" else 0), int(minute))
    return datetime.combine(datetime.strptime(day, "%B %d, %Y").date(), clock, EASTERN)


def observation_week(month_day, publication_date):
    week = datetime.strptime(f"{month_day} {publication_date.year}", "%B %d %Y").date()
    if week >= publication_date:
        week = date(publication_date.year - 1, week.month, week.day)
    if week.weekday() != 5:
        raise ValueError("DOL observation week does not end on a Saturday")
    return week


def table_values(table, label):
    row = required_match(rf"^[^\S\n]*{label}[^\S\n]+([^\n]+)", table, label, re.MULTILINE)
    cells = row.group(1).split()
    if len(cells) < 3:
        raise ValueError(f"Incomplete DOL row {label}")
    current, previous, change = (number(cell) for cell in cells[:3])
    if min(current, previous) < 0 or current - previous != change:
        raise ValueError(f"Inconsistent DOL row {label}")
    return current, previous, change


def previous_as_published(summary, category, previous):
    revision = re.search(
        rf"previous week's {category} was revised (up|down) by ({COUNT}) "
        rf"from ({COUNT}) to ({COUNT})\b", summary, re.IGNORECASE,
    )
    if revision:
        direction, difference, original, revised = revision.groups()
        adjustment = number(difference) * (1 if direction.lower() == "up" else -1)
        if number(revised) != previous or previous - number(original) != adjustment:
            raise ValueError(f"Inconsistent DOL prior-week {category} revision")
        return number(original)

    unrevised = re.search(
        rf"previous week's {category} was unrevised at ({COUNT})\b|"
        rf"previous week's unrevised {category} of ({COUNT})\b", summary, re.IGNORECASE,
    )
    if unrevised and number(next(cell for cell in unrevised.groups() if cell)) != previous:
        raise ValueError(f"Inconsistent DOL unrevised prior-week {category}")
    if unrevised or re.search(rf"previous week's unrevised {category}\b", summary):
        return previous
    if re.search(rf"previous week's {category} was (?:revised|unrevised)\b", summary):
        raise ValueError(f"Unrecognized DOL prior-week {category} revision")
    return None


def parse_release(pdf, as_of):
    if not pdf.startswith(b"%PDF-") or len(pdf) > MAX_PDF_BYTES:
        raise ValueError("DOL response is not a supported PDF")
    if as_of.utcoffset() is None:
        raise ValueError("As-of timestamp must include a UTC offset")

    reader = PdfReader(BytesIO(pdf))
    first_page = reader.pages[0].extract_text(extraction_mode="layout")
    summary = required_match(
        r"UNEMPLOYMENT INSURANCE WEEKLY CLAIMS\s+SEASONALLY ADJUSTED DATA\s+"
        r"(.*?)\n\s*\n", first_page, "initial claims summary", re.DOTALL,
    )
    release_at = release_time(" ".join(first_page[:summary.start()].split()))
    if release_at > as_of:
        raise ValueError("DOL release is later than the requested as-of timestamp")

    text = " ".join(summary.group(1).replace("’", "'").split())
    initial = required_match(
        rf"week ending ({WEEK_DATE}), the advance figure for seasonally adjusted initial claims was ({COUNT})\b",
        text, "seasonally adjusted initial claims",
    )
    average = required_match(rf"The 4-week moving average was ({COUNT})\b", text, "four-week average")
    week = observation_week(initial[1], release_at.date())
    prior_week = week - timedelta(weeks=1)

    for page in reader.pages[1:]:
        layout = page.extract_text(extraction_mode="layout")
        _, heading, tables = layout.partition("UNEMPLOYMENT INSURANCE DATA FOR REGULAR STATE PROGRAMS")
        if heading:
            table = required_match(
                rf"WEEK ENDING[^\S\n]+({WEEK_DATE})[^\S\n]+({WEEK_DATE})[^\n]*\n(.*?){ROW_END}",
                tables, "national initial claims table", re.DOTALL,
            )
            break
    else:
        raise ValueError("Missing DOL national regular state programs table")

    if (observation_week(table[1], release_at.date()) != week or
            observation_week(table[2], week) != prior_week):
        raise ValueError("DOL summary and table disagree on the observation weeks")

    current_claims, prior_claims, claims_change = table_values(table[3], r"Initial Claims \(SA\)")
    current_average, prior_average, average_change = table_values(table[3], r"4-Wk Moving Average \(SA\)")
    if current_claims != number(initial[2]) or current_average != number(average[1]):
        raise ValueError("DOL summary and table disagree on seasonally adjusted values")

    return {
        "indicator": "us_initial_unemployment_claims_sa",
        "publisher": "U.S. Department of Labor, Employment and Training Administration",
        "frequency": "weekly",
        "unit": "claims",
        "observation_week_ending": week.isoformat(),
        "previous_week_ending": prior_week.isoformat(),
        "initial_claims_advance": current_claims,
        "previous_initial_claims_in_release": prior_claims,
        "previous_initial_claims_original": previous_as_published(text, "level", prior_claims),
        "week_over_week_change": claims_change,
        "four_week_average_advance": current_average,
        "previous_four_week_average_in_release": prior_average,
        "previous_four_week_average_original": previous_as_published(text, "average", prior_average),
        "four_week_average_week_over_week_change": average_change,
        "published_at": release_at.isoformat(),
        "as_of": as_of.astimezone(timezone.utc).isoformat(),
        "release_age_days": (as_of.astimezone(EASTERN).date() - release_at.date()).days,
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_bytes": len(pdf),
    }


def fetch_pdf():
    request = Request(SOURCE_URL, headers={"Accept": "application/pdf"})
    with urlopen(request, timeout=25) as response:
        actual = urlsplit(response.geturl())
        expected = urlsplit(SOURCE_URL)
        if (actual.scheme, actual.netloc, actual.path) != (expected.scheme, expected.netloc, expected.path):
            raise ValueError("DOL response redirected away from the official release")
        if response.status != 200:
            raise ValueError(f"Unexpected DOL HTTP status {response.status}")
        return response.read(MAX_PDF_BYTES + 1), response.status, datetime.now(timezone.utc)


def write_snapshot(path, record):
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if (previous["indicator"] != record["indicator"] or
                datetime.fromisoformat(previous["published_at"]) > datetime.fromisoformat(record["published_at"])):
            raise ValueError("Refusing to replace a different indicator or a newer release")

    pending = None
    try:
        with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as f:
            pending = Path(f.name)
            f.write(json.dumps(record, indent=2) + "\n")
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--pdf", type=Path, help="replay a previously saved official PDF")
    cli.add_argument("--as-of", type=datetime.fromisoformat, help="ISO 8601 cutoff with a UTC offset")
    cli.add_argument("--output", type=Path, help="save the verified JSON to this path (default: stdout)")
    args = cli.parse_args()

    try:
        if args.pdf:
            with args.pdf.open("rb") as f:
                pdf = f.read(MAX_PDF_BYTES + 1)
            receipt = {"input_mode": "saved_pdf", "source_url": None}
        else:
            pdf, http_status, retrieved_at = fetch_pdf()
            receipt = {"input_mode": "live", "source_url": SOURCE_URL,
                       "http_status": http_status, "retrieved_at": retrieved_at.isoformat()}
        record = parse_release(pdf, args.as_of or datetime.now(timezone.utc)) | receipt
        if args.output:
            write_snapshot(args.output, record)
        else:
            print(json.dumps(record, indent=2))
    except (ValueError, OSError, KeyError, IndexError, PdfReadError) as exc:
        cli.exit(1, f"V70 initial claims: {exc}\n")


if __name__ == "__main__":
    main()
