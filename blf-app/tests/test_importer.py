from datetime import date

import pytest

from blf_app.importer import parse_date, parse_weight, read_weights

TODAY = date(2026, 11, 3)


def dates_and_kg(result):
    return [(r["date"].isoformat(), r["kg"]) for r in result.rows]


@pytest.mark.parametrize("text, order, expected", [
    ("2026-10-01", "dmy", date(2026, 10, 1)),
    ("2026-10-01T07:12:33Z", "dmy", date(2026, 10, 1)),
    ("01/10/2026", "dmy", date(2026, 10, 1)),
    ("10/01/2026", "mdy", date(2026, 10, 1)),
    ("1.10.26", "dmy", date(2026, 10, 1)),
    ("1 Oct 2026", "dmy", date(2026, 10, 1)),
    ("October 1st, 2026", "dmy", date(2026, 10, 1)),
    ("Thu 1 Oct 2026 07:30", "dmy", date(2026, 10, 1)),
    ("31/02/2026", "dmy", None),
    ("yesterday", "dmy", None),
])
def test_parse_date(text, order, expected):
    assert parse_date(text, order) == expected


@pytest.mark.parametrize("text, unit, kg", [
    ("82.4", "kg", 82.4),
    ("82,4", "kg", 82.4),
    ("181.6 lb", "kg", 82.37),
    ("181.6", "lb", 82.37),
    ("13st 6lb", "kg", 85.28),
    ("13 st 6", "kg", 85.28),
    ("13.5", "st", 85.73),
    ("heavy", "kg", None),
])
def test_parse_weight(text, unit, kg):
    result = parse_weight(text, unit)
    assert (result is None) if kg is None else round(result, 2) == kg


def test_header_with_pounds_and_other_columns():
    r = read_weights("Date,Weight (lbs),BMI,Fat\n10/01/2026,187.8,26.3,22\n", order="mdy", today=TODAY)
    assert dates_and_kg(r) == [("2026-10-01", 85.2)]
    assert "pounds" in r.columns


def test_stone_and_pound_columns():
    r = read_weights("Date;Stone;Pounds\n01/10/2026;13;6\n", today=TODAY)
    assert dates_and_kg(r) == [("2026-10-01", 85.3)]


def test_keeps_first_reading_each_day_and_sorts():
    r = read_weights('Date,"Weight (kg)"\n2026-10-02 07:00,85.0\n2026-10-01 07:00,85.2\n2026-10-01 21:00,86.0\n', today=TODAY)
    assert dates_and_kg(r) == [("2026-10-01", 85.2), ("2026-10-02", 85.0)]
    assert r.merged == 1


def test_pasted_rows_without_header_and_bad_lines():
    r = read_weights("3 Oct 2026  13st 6lb\n10 Oct 2026 84.6 kg\nbad line\n2027-01-01 80\n2026-10-11 9\n", today=TODAY)
    assert dates_and_kg(r) == [("2026-10-03", 85.3), ("2026-10-10", 84.6)]
    reasons = [s["reason"] for s in r.skipped]
    assert any("isn't a date" in x for x in reasons)
    assert any("future" in x for x in reasons)
    assert any("looks wrong" in x for x in reasons)


def test_unrecognised_header_falls_back_to_first_columns():
    r = read_weights("Datum;Gewicht\n01.10.2026;85,2\n", today=TODAY)
    assert dates_and_kg(r) == [("2026-10-01", 85.2)]


def test_excel_byte_order_mark():
    r = read_weights("﻿Date,Weight\n2026-10-01,85.2\n", today=TODAY)
    assert dates_and_kg(r) == [("2026-10-01", 85.2)]


def test_header_without_weight_column():
    r = read_weights("Date,Steps\n2026-10-01,9000\n", today=TODAY)
    assert r.rows == [] and r.skipped
