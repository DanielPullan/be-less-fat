"""Read weigh-ins exported from other apps (a CSV file, or rows pasted in).

Each app exports differently, so this is forgiving:
- the delimiter is guessed (comma, semicolon, tab or pipe)
- a header row is optional; if there is one, the date and weight columns are found by name
  ("Date", "Weight (kg)", "Body Mass", "lbs"...), otherwise the first column is the date and the
  first number after it is the weight
- dates can be 2026-11-03, 03/11/2026 (or 11/03/2026 when date order is US), 3 Nov 2026,
  November 3, 2026, with or without a time after them
- weights can be kg, lb or stones ("13st 6lb", "13 st 6", or a stone column); the unit comes from
  the header or the value itself, otherwise the unit the person picked
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

KG_PER_LB = 0.45359237
LB_PER_STONE = 14
UNITS = {"kg": "Kilograms (kg)", "lb": "Pounds (lb)", "st": "Stones (st)"}
DATE_ORDERS = {"dmy": "Day first (UK): 03/11/2026 is 3 November", "mdy": "Month first (US): 11/03/2026 is 3 November"}

MIN_KG, MAX_KG = 20, 400
MAX_ROWS = 20000

DATE_HEADERS = ("date", "day", "time", "when", "timestamp", "logged", "recorded")
WEIGHT_HEADERS = ("weight", "body mass", "mass", "kg", "lb", "lbs", "pounds", "stone", "kilograms")
SKIP_WEIGHT_HEADERS = ("fat", "bmi", "muscle", "bone", "water", "lean", "goal", "target", "change", "diff")

TEXT_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%d-%b-%Y", "%d-%B-%Y", "%a %d %b %Y", "%a %b %d %Y")
STONES_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:st|stone|stones)\s*(?:(\d+(?:\.\d+)?)\s*(?:lb|lbs|pounds?)?)?\s*$", re.I)
NUMBER_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(kg|kgs|kilograms?|lb|lbs|pounds?|st|stones?)?\s*$", re.I)


@dataclass
class ImportResult:
    rows: list = field(default_factory=list)      # [{"date": date, "kg": float, "line": int}]
    skipped: list = field(default_factory=list)   # [{"line": int, "text": str, "reason": str}]
    merged: int = 0                               # extra readings on a day already in the file
    columns: str = ""                             # what we decided the columns were, for the preview


def parse_date(text, order="dmy"):
    """A date from many common formats, ignoring any time after it. None if it isn't one."""
    text = text.strip().strip('"').strip()
    if not text:
        return None
    # ISO, with an optional time: 2026-11-03, 2026-11-03T07:30:00Z, 2026-11-03 07:30
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T\s].*)?$", text)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return _safe_date(y, mo, d)
    # 03/11/2026, 3.11.26, 11-03-2026 07:30
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})(?:[T\s,].*)?$", text)
    if m:
        a, b, y = (int(g) for g in m.groups())
        if y < 100:
            y += 2000
        d, mo = (a, b) if order == "dmy" else (b, a)
        return _safe_date(y, mo, d)
    # Text months: 3 Nov 2026, November 3, 2026, Tue 3 Nov 2026 07:30
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.replace(",", " "))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = cleaned.split(" ")
    for n in (4, 3):
        candidate = " ".join(words[:n])
        for fmt in TEXT_DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _safe_date(y, mo, d):
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_weight(text, unit="kg"):
    """Kilograms from a weight like 82.4, 181.6 lb, 13st 6lb or 82,4. None if it isn't one."""
    text = text.strip().strip('"').strip()
    if not text:
        return None
    m = STONES_RE.match(text)
    if m:
        stones = float(m.group(1))
        pounds = float(m.group(2) or 0)
        return (stones * LB_PER_STONE + pounds) * KG_PER_LB
    m = NUMBER_RE.match(text)
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    suffix = (m.group(2) or "").lower()
    if suffix.startswith("k"):
        unit = "kg"
    elif suffix.startswith(("l", "p")):
        unit = "lb"
    elif suffix.startswith("st"):
        unit = "st"
    if unit == "lb":
        return value * KG_PER_LB
    if unit == "st":
        return value * LB_PER_STONE * KG_PER_LB
    return value


def _unit_from_header(header):
    h = header.lower()
    if re.search(r"\b(lb|lbs|pounds?)\b", h):
        return "lb"
    if re.search(r"\b(st|stones?)\b", h):
        return "st"
    if re.search(r"\b(kg|kgs|kilograms?)\b", h):
        return "kg"
    return None


def _find_columns(header):
    """(date column, weight column, unit from header, extra pounds column for stone+lb exports)."""
    names = [h.strip().lower() for h in header]
    date_col = next((i for i, h in enumerate(names) if any(k in h for k in DATE_HEADERS)), None)
    weight_cols = [i for i, h in enumerate(names)
                   if any(k in h for k in WEIGHT_HEADERS) and not any(k in h for k in SKIP_WEIGHT_HEADERS)
                   and i != date_col]
    if date_col is None or not weight_cols:
        return None
    # Prefer a column that says "weight"; otherwise the first unit-named one
    weight_col = next((i for i in weight_cols if "weight" in names[i] or "mass" in names[i]), weight_cols[0])
    unit = _unit_from_header(names[weight_col])
    pounds_col = None
    if unit == "st":
        pounds_col = next((i for i in weight_cols if i != weight_col and _unit_from_header(names[i]) == "lb"), None)
    return date_col, weight_col, unit, pounds_col


def read_weights(text, unit="kg", order="dmy", today=None):
    """Parse an export into one reading per day. Rows that can't be read are listed with a reason."""
    today = today or date.today()
    result = ImportResult()
    text = text.lstrip("﻿")  # Excel's byte order mark
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return result
    if len(lines) > MAX_ROWS + 1:
        result.skipped.append({"line": MAX_ROWS + 2, "text": "", "reason": f"Only the first {MAX_ROWS} rows are read"})
        lines = lines[: MAX_ROWS + 1]

    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "," if "," in lines[0] else ("\t" if "\t" in lines[0] else ";")
    # "3 Nov 2026 82.4" pasted with spaces only: split on two or more spaces, or a single space before the number
    records = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    if all(len(r) == 1 for r in records):
        records = [_split_spaces(r[0]) for r in records]

    columns = None
    start = 0
    first = records[0]
    if parse_date(first[0] if first else "", order) is None:
        columns = _find_columns(first)
        start = 1
        if columns is None:
            # A header we don't recognise (another language, say): fine if the rows under it start with a date
            if len(records) > 1 and records[1] and parse_date(records[1][0], order) is not None:
                columns = (0, None, None, None)
                result.columns = (f"Header “{delimiter.join(first)}” not recognised: dates from the first column, "
                                  "weights from the first number after it")
            else:
                result.skipped.append({"line": 1, "text": delimiter.join(first),
                                       "reason": "Couldn't find a date column and a weight column in this header"})
                return result

    if columns and columns[1] is None:
        date_col, weight_col, header_unit, pounds_col = columns
    elif columns:
        date_col, weight_col, header_unit, pounds_col = columns
        result.columns = (f"Dates from “{first[date_col].strip()}”, weights from “{first[weight_col].strip()}”"
                          + (f" + “{first[pounds_col].strip()}”" if pounds_col is not None else "")
                          + (f" (in {UNITS[header_unit].split(' ')[0].lower()})" if header_unit else ""))
    else:
        date_col, weight_col, header_unit, pounds_col = 0, None, None, None
        result.columns = "No header row: dates from the first column, weights from the first number after it"
    row_unit = header_unit or unit

    by_day = {}
    for number, record in enumerate(records[start:], start=start + 1):
        raw = delimiter.join(record)
        if date_col >= len(record):
            result.skipped.append({"line": number, "text": raw, "reason": "Missing the date"})
            continue
        day = parse_date(record[date_col], order)
        if day is None:
            result.skipped.append({"line": number, "text": raw, "reason": f"“{record[date_col].strip()}” isn't a date we can read"})
            continue
        if day > today:
            result.skipped.append({"line": number, "text": raw, "reason": "Date is in the future"})
            continue

        if weight_col is not None:
            cell = record[weight_col] if weight_col < len(record) else ""
            if pounds_col is not None and pounds_col < len(record) and record[pounds_col].strip():
                cell = f"{cell}st {record[pounds_col]}lb"
            kg = parse_weight(cell, row_unit)
        else:
            cell = next((c for c in record[1:] if parse_weight(c, row_unit) is not None), "")
            kg = parse_weight(cell, row_unit)
        if kg is None:
            result.skipped.append({"line": number, "text": raw, "reason": "No weight on this row" if not cell.strip() else f"“{cell.strip()}” isn't a weight we can read"})
            continue
        if not MIN_KG <= kg <= MAX_KG:
            result.skipped.append({"line": number, "text": raw, "reason": f"{kg:.1f} kg looks wrong (check the unit)"})
            continue

        if day in by_day:
            result.merged += 1  # keep the first reading of the day
            continue
        by_day[day] = {"date": day, "kg": round(kg, 1), "line": number}

    result.rows = sorted(by_day.values(), key=lambda r: r["date"])
    return result


def _split_spaces(line):
    parts = re.split(r"\s{2,}", line.strip())
    if len(parts) > 1:
        return parts
    # "2026-11-03 82.4" or "3 Nov 2026 82.4 kg": the weight is the last number (and any unit after it)
    m = re.match(r"^(.*?)[\s]+(\d+(?:[.,]\d+)?\s*(?:kg|kgs|lb|lbs|st)?)$", line.strip(), re.I)
    return [m.group(1), m.group(2)] if m else [line]
