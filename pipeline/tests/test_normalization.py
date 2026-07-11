"""Field-normalisation contracts for load_transcripts."""

from datetime import date

import load_transcripts as lt


def test_normalize_quarter_recognises_q_forms():
    assert lt.normalize_quarter("Q1") == "Q1"
    assert lt.normalize_quarter("q3") == "Q3"
    assert lt.normalize_quarter("quarter 2") == "Q2"


def test_normalize_quarter_bare_digit_becomes_q():
    assert lt.normalize_quarter("4") == "Q4"
    assert lt.normalize_quarter(3) == "Q3"


def test_normalize_quarter_empty_is_none():
    assert lt.normalize_quarter(None) is None
    assert lt.normalize_quarter("") is None


def test_to_iso_date_from_string_and_date():
    assert lt.to_iso_date("2021-05-04") == "2021-05-04"
    assert lt.to_iso_date("2021-05-04T00:00:00") == "2021-05-04"
    assert lt.to_iso_date(date(2021, 5, 4)) == "2021-05-04"


def test_to_iso_date_empty_is_none():
    assert lt.to_iso_date(None) is None
    assert lt.to_iso_date("") is None
