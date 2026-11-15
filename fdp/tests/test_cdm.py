"""
test_cdm.py — Contract tests for the FDGA canonical data model.

These cover the normalization rules that absorb source drift. Each case here
is a real value observed in the 2000-2024 OpenElections Georgia files; if one
of these regresses, a whole cycle silently mis-parses.

    uv run --project fdp pytest fdp/tests/test_cdm.py -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from fdp.cdm import aggregate, corrections, schema, validate


# ---------------------------------------------------------------------------
# Office normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # Short form, used in most cycles.
    ("State House", "state_house"),
    ("State Senate", "state_senate"),
    ("U.S. House", "us_house"),
    ("U.S. Senate", "us_senate"),
    ("President", "president"),
    ("Governor", "governor"),
    # Long form, used in 2016 and 2018.
    ("State Representative", "state_house"),
    ("State Senator", "state_senate"),
    ("U.S. Representative", "us_house"),
    ("United States Senator", "us_senate"),
    ("President of the United States", "president"),
    # 2020 special Senate seat maps to the same office.
    ("U.S. Senate (Special)", "us_senate"),
    # Deliberately out of scope.
    ("Attorney General", None),
    ("Lieutenant Governor", None),
    ("Public Service Commission", None),
    ("District Attorney", None),
    ("Vice President", None),
    (None, None),
    ("", None),
])
def test_normalize_office(raw, expected):
    assert schema.normalize_office(raw) == expected


def test_ballot_questions_with_markup_are_dropped():
    """2016 embeds HTML in ballot-question office names."""
    raw = ("Constitutional Amendment #1<br>Provides greater flexibility and "
           "state accountability to fix failing schools")
    assert schema.normalize_office(raw) is None


def test_special_seat_detection():
    assert schema.is_special_seat("U.S. Senate (Special)")
    assert not schema.is_special_seat("U.S. Senate")


# ---------------------------------------------------------------------------
# Party normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Republican", "R"), ("Democrat", "D"), ("Democratic", "D"),
    ("Libertarian", "L"), ("Green", "G"), ("Independent", "I"),
    ("Write-In", "W"), ("Nonpartisan", "N"),
    # Three-letter codes (2016, 2018).
    ("REP", "R"), ("DEM", "D"), ("LIB", "L"), ("IND", "I"),
    # Single letters (2018).
    ("R", "R"), ("D", "D"), ("L", "L"),
    # The stray-paren artifact: ~25k rows across 2016 and 2018.
    ("(REP", "R"), ("(DEM", "D"),
    # One 2016 row bled a candidate name into the party column; it still
    # resolves because matching is on substring.
    ("J. W. MORROW JR (REP", "R"),
    # Unknown values bucket to Other rather than raising.
    (None, "O"), ("", "O"), ("Unity Party", "O"),
])
def test_normalize_party(raw, expected):
    assert schema.normalize_party(raw) == expected


def test_green_does_not_match_the_r_in_its_name():
    """Substring matching is ordered so 'GREEN' cannot resolve to 'R'."""
    assert schema.normalize_party("Green") == "G"
    assert schema.normalize_party("GRN") == "G"


def test_write_in_does_not_match_independent():
    assert schema.normalize_party("Write-In") == "W"


# ---------------------------------------------------------------------------
# District normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,office,expected", [
    ("1", "state_house", "001"),
    ("01", "state_house", "001"),
    ("180", "state_house", "180"),
    ("  14 ", "us_house", "014"),
    # A CSV round-trip through a float column yields '1.0'.
    ("1.0", "state_senate", "001"),
    # Statewide offices carry no district.
    ("", "president", ""),
    ("5", "president", ""),
    (None, "state_house", ""),
    ("n/a", "state_house", ""),
])
def test_normalize_district(raw, office, expected):
    assert schema.normalize_district(raw, office) == expected


# ---------------------------------------------------------------------------
# Candidate names and incumbency
# ---------------------------------------------------------------------------

def test_normalize_candidate_collapses_doubled_quotes():
    """The 2022 export doubles embedded quotes."""
    assert schema.normalize_candidate('Earl L. ""Buddy"" Carter') == \
        'Earl L. "Buddy" Carter'


def test_normalize_candidate_collapses_whitespace():
    assert schema.normalize_candidate("  JOHN   LEWIS  ") == "JOHN LEWIS"


def test_detect_incumbent():
    assert schema.detect_incumbent("SANFORD BISHOP (I)")
    assert schema.detect_incumbent("Brian Kemp (I) (Rep)")
    assert not schema.detect_incumbent("Patti Hewitt (Dem)")


# ---------------------------------------------------------------------------
# Name canonicalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("PAUL C. BROUN", "BROUN"),
    ("PAUL BROUN", "BROUN"),
    # Generational suffixes are ignored.
    ("H. JOHNSON JR.", "JOHNSON"),
    ("H. JOHNSON JR", "JOHNSON"),
    ("HENRY C. 'HANK' JOHNSON", "JOHNSON"),
    # Hyphenated surnames match across spellings, because punctuation
    # becomes whitespace before tokenizing.
    ("D. D-HAIGLER", "HAIGLER"),
    ("D DAW-HAIGLER", "HAIGLER"),
])
def test_surname_extraction(name, expected):
    assert corrections._surname(name) == expected


def _facts(rows: list[dict]) -> pd.DataFrame:
    base = {
        "election_date": "2012-11-06", "cycle_year": 2012,
        "election_type": "general", "office": "us_house", "district": "004",
        "county": "Dekalb", "party_raw": "Democrat", "party": "D",
        "source_id": "test", "source_row": 0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])[schema.FACT_COLUMNS]


def test_canonicalize_merges_name_variants():
    """Hank Johnson appears four ways in the 2012 CD-4 source."""
    facts = _facts([
        {"candidate_name": "HENRY C. 'HANK' JOHNSON", "votes": 135971,
         "county": "Dekalb"},
        {"candidate_name": "HENRY JOHNSON", "votes": 32990, "county": "Gwinnett"},
        {"candidate_name": "H. JOHNSON JR.", "votes": 21139, "county": "Rockdale"},
        {"candidate_name": "H. JOHNSON JR", "votes": 18761, "county": "Newton"},
    ])
    merged, report = corrections.canonicalize_names(facts)
    assert merged["candidate_name"].nunique() == 1
    assert merged["candidate_name"].iloc[0] == "HENRY C. 'HANK' JOHNSON"
    assert merged["votes"].sum() == facts["votes"].sum()
    assert len(report) == 3


def test_canonicalize_keeps_different_parties_apart():
    """Same surname, different party — two people, never merged."""
    facts = _facts([
        {"candidate_name": "JOHN SMITH", "votes": 100, "party": "D"},
        {"candidate_name": "J. SMITH", "votes": 90, "party": "R",
         "party_raw": "Republican"},
    ])
    merged, report = corrections.canonicalize_names(facts)
    assert merged["candidate_name"].nunique() == 2
    assert len(report) == 0


def test_canonicalize_keeps_different_districts_apart():
    facts = _facts([
        {"candidate_name": "JOHN SMITH", "votes": 100, "district": "004"},
        {"candidate_name": "J. SMITH", "votes": 90, "district": "005"},
    ])
    merged, _ = corrections.canonicalize_names(facts)
    assert merged["candidate_name"].nunique() == 2


# ---------------------------------------------------------------------------
# Aggregation policy
# ---------------------------------------------------------------------------

def _contest(cands: list[tuple[str, str, int]], office="state_house",
             district="001") -> pd.DataFrame:
    return _facts([
        {"candidate_name": n, "party": p, "votes": v,
         "office": office, "district": district}
        for n, p, v in cands
    ])


def test_write_ins_do_not_make_a_race_contested():
    """2008 CD-5: John Lewis vs two write-ins totalling 93 votes."""
    facts = _contest([
        ("John Lewis", "D", 231368),
        ("Jeanne Fitzmaurice", "W", 12),
        ("Shira Kash", "W", 81),
    ], office="us_house", district="005")
    contests = aggregate.build_contests(facts)
    assert bool(contests["is_uncontested"].iloc[0]) is True


def test_minor_party_opposition_splits_the_two_definitions():
    """A Republican facing only a Libertarian: contested strictly, not by major."""
    facts = _contest([("R Candidate", "R", 60000), ("L Candidate", "L", 10000)])
    contests = aggregate.build_contests(facts)
    assert bool(contests["is_uncontested"].iloc[0]) is False
    assert bool(contests["is_uncontested_major"].iloc[0]) is True


def test_competitive_uses_the_declared_threshold():
    facts = _contest([("R", "R", 5300), ("D", "D", 4700)])   # 53.0% winner
    contests = aggregate.build_contests(facts)
    assert bool(contests["is_competitive"].iloc[0]) is True

    facts = _contest([("R", "R", 6000), ("D", "D", 4000)])   # 60.0% winner
    contests = aggregate.build_contests(facts)
    assert bool(contests["is_competitive"].iloc[0]) is False


def test_uncontested_races_are_never_competitive():
    facts = _contest([("R", "R", 20000)])
    contests = aggregate.build_contests(facts)
    assert bool(contests["is_competitive"].iloc[0]) is False


def test_winner_is_the_candidate_with_most_votes():
    facts = _contest([("Loser", "R", 4000), ("Winner", "D", 6000)])
    contests = aggregate.build_contests(facts)
    row = contests.iloc[0]
    assert row["winner_name"] == "Winner"
    assert row["winner_party"] == "D"
    assert row["margin"] == 2000


def test_multi_member_chamber_suppresses_seat_counts():
    """2002 state house: seats are not derivable without a post identifier."""
    facts = _contest([("A", "R", 100), ("B", "D", 90)])
    facts["cycle_year"] = 2002
    facts["election_date"] = "2002-11-05"
    contests = aggregate.build_contests(facts)
    cy = aggregate.build_chamber_year(contests, multi_member={(2002, "state_house")})
    row = cy.iloc[0]
    assert bool(row["seats_derivable"]) is False
    assert pd.isna(row["seats_r"])
    # Votes stay valid even where seats cannot be attributed.
    assert row["votes_total"] == 190


def test_congressional_seat_count_changes_with_apportionment():
    """Georgia gained a 14th seat in 2012."""
    assert aggregate.expected_seats(2010, "us_house") == 13
    assert aggregate.expected_seats(2012, "us_house") == 14
    assert aggregate.expected_seats(2024, "state_house") == 180


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_grain_uniqueness_check_catches_duplicates():
    facts = _facts([
        {"candidate_name": "A", "votes": 10},
        {"candidate_name": "A", "votes": 20},
    ])
    result = validate.check_grain_unique(facts)
    assert result[0].severity == "FAIL"


def test_party_domain_check_passes_on_known_parties():
    facts = _facts([{"candidate_name": "A", "votes": 10, "party": "D"}])
    assert validate.check_party_domain(facts)[0].severity == "PASS"


def test_documented_gaps_downgrade_from_fail_to_known():
    """A gap listed in KNOWN_GAPS must not fail the build."""
    assert (2002, "state_house") in \
        {(g.cycle_year, g.office) for g in validate.KNOWN_GAPS}
    severity, reason = validate._severity_for(2002, "state_house")
    assert severity == "KNOWN"
    assert "multi-member" in reason

    # Anything undocumented is still a hard failure.
    assert validate._severity_for(2024, "state_house")[0] == "FAIL"
