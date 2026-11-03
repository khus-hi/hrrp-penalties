"""The SQL macros every staging model relies on."""
import pytest


@pytest.mark.parametrize("raw, expected", [
    ("10001", "010001"),      # leading zero dropped by a spreadsheet
    (" 22010b ", "22010B"),   # whitespace and lower case
    ("010001", "010001"),
    ("1234567", None),        # too long to be a CCN
    ("N/A", None),
])
def test_clean_ccn(con, raw, expected):
    assert con.execute("SELECT clean_ccn(?)", [raw]).fetchone()[0] == expected


@pytest.mark.parametrize("raw, expected", [
    ("0.9965", 0.9965),
    ("1,234", 1234.0),
    ("12.5%", 12.5),
    ("$2,000", 2000.0),
    ("N/A", None),
    ("", None),
])
def test_to_num(con, raw, expected):
    assert con.execute("SELECT to_num(?)", [raw]).fetchone()[0] == expected


@pytest.mark.parametrize("cms, census", [
    ("ST. LOUIS", "St. Louis County"),
    ("SAINT LOUIS", "St. Louis County"),
    ("ORLEANS", "Orleans Parish"),
    ("JUNEAU", "Juneau City and Borough"),
])
def test_norm_county_matches_cms_and_census_spellings(con, cms, census):
    a, b = con.execute("SELECT norm_county(?), norm_county(?)", [cms, census]).fetchone()
    assert a == b
