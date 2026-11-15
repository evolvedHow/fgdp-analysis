"""
schema.py — The Georgia General Assembly canonical data model (CDM).

This module is the contract. Adapters read wildly varying source formats and
must emit exactly ``FACT_COLUMNS``; everything downstream reads only the CDM
and never touches a source file. When a source format changes, a new adapter is
written and nothing here moves.

Grain of ``facts``: one row per (election_date, office, district, county, candidate).

Design rule — facts in, judgments out
------------------------------------
The CDM carries only what the source states. Anything requiring a policy
decision is computed in the aggregate layer, where the rule is visible and
changeable in one place:

  * "competitive"    — threshold is a policy choice (see COMPETITIVE_LIMIT)
  * "uncontested"    — depends on whether minor-party-only opposition counts
  * two-party share  — the denominator is a choice
  * cycle rollup of runoffs into a prior year — a choice

Mechanical properties (winner = most votes, margin, vote totals) are safe to
derive and live in ``aggregate.py``.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Fact table
# ---------------------------------------------------------------------------

FACT_COLUMNS: list[str] = [
    "election_date",    # ISO date of the election, e.g. 2024-11-05
    "cycle_year",       # analytic year the row rolls into (int)
    "election_type",    # general | runoff | special
    "office",           # see OFFICES — normalized code
    "district",         # zero-padded 3-char, e.g. '001'; '' for statewide
    "county",           # Georgia county name, title case
    "candidate_name",   # as printed by the source, whitespace-normalized
    "party_raw",        # exactly as the source wrote it (audit trail)
    "party",            # see PARTIES — normalized single letter
    "votes",            # int, >= 0
    "source_id",        # FK -> the _manifest table
    "source_row",       # 0-based row index within the source file
]

# Column dtypes used when the CDM is read back from CSV, so a round-trip
# through Sheets or a text file cannot silently retype anything.
FACT_DTYPES: dict[str, str] = {
    "election_date": "string",
    "cycle_year": "int64",
    "election_type": "string",
    "office": "string",
    "district": "string",
    "county": "string",
    "candidate_name": "string",
    "party_raw": "string",
    "party": "string",
    "votes": "int64",
    "source_id": "string",
    "source_row": "int64",
}

# ---------------------------------------------------------------------------
# Offices
# ---------------------------------------------------------------------------
# Scope rule (fgdp/CLAUDE.md): score president, governor, senate, us-house and
# state legislative races only. Attorney General, Secretary of State, Lt.
# Governor, PSC, and the various commissioners are deliberately excluded — they
# are not part of the seats-vs-votes analysis and carry their own drift.

OFFICES: dict[str, dict] = {
    "president":    {"chamber": None,           "districted": False, "seats": None},
    "us_senate":    {"chamber": None,           "districted": False, "seats": None},
    "governor":     {"chamber": None,           "districted": False, "seats": None},
    "us_house":     {"chamber": "us_house",     "districted": True,  "seats": "cd"},
    "state_senate": {"chamber": "state_senate", "districted": True,  "seats": 56},
    "state_house":  {"chamber": "state_house",  "districted": True,  "seats": 180},
}

#: Chambers that make up the seats-vs-votes analysis, in display order.
CHAMBERS: list[str] = ["us_house", "state_senate", "state_house"]

#: Georgia's congressional delegation size by cycle. Georgia gained a 14th seat
#: in the 2010 apportionment, first elected in 2012.
CONGRESSIONAL_SEATS: dict[int, int] = {
    2000: 11, 2002: 13, 2004: 13, 2006: 13, 2008: 13, 2010: 13,
    2012: 14, 2014: 14, 2016: 14, 2018: 14, 2020: 14, 2022: 14, 2024: 14,
}

# Source office strings vary by cycle: 'State House' (most years) vs 'State
# Representative' (2016, 2018), 'U.S. Senate' vs 'United States Senator', and
# so on. Matching is done on a normalized (lowercased, punctuation-stripped)
# form so we do not have to enumerate every spacing variant.
_OFFICE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(us|u s|united states) (house|representative)"), "us_house"),
    (re.compile(r"^(us|u s|united states) (senate|senator)"),       "us_senate"),
    (re.compile(r"^state (house|representative)"),                  "state_house"),
    (re.compile(r"^state (senate|senator)"),                        "state_senate"),
    (re.compile(r"^president"),                                     "president"),
    (re.compile(r"^governor"),                                      "governor"),
]


def normalize_office(raw: str | None) -> str | None:
    """Map a source office string to a CDM office code, or None if out of scope.

    Returns None for offices we deliberately exclude (Attorney General, PSC,
    ballot questions, District Attorney, Lieutenant Governor, ...) as well as
    for anything unrecognized. Callers filter on None rather than raising, so a
    new down-ballot office appearing in a source file is skipped rather than
    aborting the build; the validator reports what was dropped.
    """
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    # 2016 embeds HTML in ballot-question office names; drop anything with markup.
    if "<" in s:
        return None
    s = re.sub(r"[.,]", "", s)
    s = re.sub(r"\s+", " ", s)
    # 'U.S. Senate (Special)' — the 2020 Loeffler/Warnock seat. Same office,
    # different seat; election_type carries the distinction.
    s = re.sub(r"\s*\(special\)\s*$", "", s)
    # 'President of the United States' (2016) -> 'president'
    for pat, code in _OFFICE_PATTERNS:
        if pat.match(s):
            return code
    return None


def is_special_seat(raw: str | None) -> bool:
    """True when the source office string marks a special election seat."""
    return bool(raw) and "(special)" in str(raw).strip().lower()


# ---------------------------------------------------------------------------
# Parties
# ---------------------------------------------------------------------------
# Source party values across the 13 cycles include full names ('Republican'),
# three-letter codes ('REP'), single letters ('R'), and a stray-paren artifact
# in the 2016 and 2018 files ('(REP', '(DEM' — ~25k rows). One 2016 row has a
# candidate name bled into the party column ('J. W. MORROW JR (REP'), which
# still resolves correctly because we match on substring.

PARTIES: dict[str, str] = {
    "R": "Republican",
    "D": "Democratic",
    "L": "Libertarian",
    "G": "Green",
    "I": "Independent",
    "W": "Write-In",
    "N": "Nonpartisan",
    "O": "Other",
}

#: Parties treated as major for seats-vs-votes analysis.
MAJOR_PARTIES: tuple[str, str] = ("R", "D")

# Ordered longest-first so 'REP' is tested before 'R' and we do not match the
# 'R' inside 'GREEN' or 'WRITE-IN'.
_PARTY_SUBSTRINGS: list[tuple[str, str]] = [
    ("REPUBLICAN", "R"), ("DEMOCRATIC", "D"), ("DEMOCRAT", "D"),
    ("LIBERTARIAN", "L"), ("NONPARTISAN", "N"), ("INDEPENDENT", "I"),
    ("WRITEIN", "W"), ("WRITE IN", "W"), ("GREEN", "G"),
    ("REP", "R"), ("DEM", "D"), ("LIB", "L"), ("GRN", "G"),
    ("IND", "I"), ("NOP", "N"),
]

_PARTY_EXACT: dict[str, str] = {
    "R": "R", "D": "D", "L": "L", "G": "G", "I": "I", "W": "W", "N": "N",
}


def normalize_party(raw: str | None) -> str:
    """Map a source party string to a single-letter CDM party code.

    Unrecognized values fall through to 'O' (Other) rather than raising — a
    row with an odd party label is still a real vote and should be counted in
    turnout totals. The validator reports the distinct raw values that landed
    in 'O' so genuinely new parties can be added deliberately.
    """
    if raw is None:
        return "O"
    s = str(raw).strip().upper()
    if not s or s in {"NAN", "NONE"}:
        return "O"
    # Strip the stray-paren artifact and any other punctuation noise.
    s = re.sub(r"[^A-Z0-9 ]", "", s).strip()
    if not s:
        return "O"
    if s in _PARTY_EXACT:
        return _PARTY_EXACT[s]
    for needle, code in _PARTY_SUBSTRINGS:
        if needle in s:
            return code
    return "O"


# ---------------------------------------------------------------------------
# Districts
# ---------------------------------------------------------------------------

def normalize_district(raw: str | None, office: str) -> str:
    """Zero-pad a district number to 3 characters; '' for statewide offices.

    Sources write districts as '1', '01', '001', ' 1 ', and occasionally with a
    stray decimal ('1.0') when a CSV round-tripped through a float column.
    """
    if not OFFICES[office]["districted"]:
        return ""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none"}:
        return ""
    s = re.sub(r"\.0+$", "", s)          # '1.0' -> '1'
    digits = re.sub(r"[^0-9]", "", s)
    if not digits:
        return ""
    return digits.zfill(3)


# ---------------------------------------------------------------------------
# Candidate names and incumbency
# ---------------------------------------------------------------------------

_INCUMBENT_MARKERS = (
    re.compile(r"\(\s*I\s*\)"),        # 'SANFORD BISHOP (I)'
    re.compile(r"\(\s*Incumbent\s*\)", re.I),
)


def normalize_candidate(raw: str | None) -> str:
    """Collapse whitespace and strip the doubled quotes seen in some exports."""
    if raw is None:
        return ""
    s = str(raw).replace('""', '"').strip()
    return re.sub(r"\s+", " ", s)


def detect_incumbent(raw: str | None) -> bool | None:
    """Detect an '(I)' incumbency marker in a candidate name.

    Returns None rather than False when the whole source file carries no
    markers at all — the caller decides, since 'no marker anywhere' means the
    source does not report incumbency rather than 'nobody was an incumbent'.
    A False here would silently assert the latter.
    """
    if raw is None:
        return None
    return any(p.search(str(raw)) for p in _INCUMBENT_MARKERS)


# ---------------------------------------------------------------------------
# Analysis parameters
# ---------------------------------------------------------------------------
# The legacy workbook stored this in a named range (Percentages!$T$22) and
# referenced it from ~3,000 copied IF formulas, several of which drifted. Here
# it is one constant, applied in one place in aggregate.py.

#: A race is "competitive" when the winner's share of the vote is at or below
#: this value. Matches the legacy workbook's ``Competitive_Limit``.
COMPETITIVE_LIMIT: float = 0.535

#: Additional thresholds materialized alongside the default, so the UI layer
#: can offer a selector without recomputing anything.
COMPETITIVE_LIMITS: tuple[float, ...] = (0.52, 0.535, 0.55, 0.60)
