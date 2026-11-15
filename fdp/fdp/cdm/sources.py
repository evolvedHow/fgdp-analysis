"""
sources.py — Registry of raw election-result sources, one entry per cycle.

This registry is the only place that knows what shape a source file has. When
the Redistricting Data Hub / OpenElections changes an export format, a new
entry is added here (or an existing one amended) and nothing downstream of the
CDM moves.

Source: OpenElections for Georgia — https://github.com/openelections/openelections-data-ga
Fetched as a repository tarball by ``scripts/build_fdga_cdm.py --fetch``.

Format drift actually observed across the 13 general elections
--------------------------------------------------------------
  2000-2010  county grain, single file, explicit ``votes`` column
  2012       precinct grain, single file, no total — four vote-mode columns
  2014       county grain, single file, no total — four vote-mode columns
  2016       county grain, single file, ``votes`` present + four mode columns
  2018       precinct grain, **159 per-county files**, ``votes`` + six modes
  2020-2024  precinct grain (2024 also county), no total — four mode columns

Office and party spellings drift independently of the column layout and are
handled by ``schema.normalize_office`` / ``schema.normalize_party``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    """One raw source file set for one election."""

    source_id: str
    #: ISO date of the election.
    election_date: str
    #: Analytic year this source rolls into.
    cycle_year: int
    #: general | runoff | special
    election_type: str
    #: Glob patterns, relative to the OpenElections repo root. A pattern may
    #: match many files (2018 ships one file per county).
    patterns: tuple[str, ...]
    #: Name of a column holding the total vote, when the source provides one.
    votes_total_column: str | None = None
    #: Columns summed to produce the total when ``votes_total_column`` is None.
    votes_mode_columns: tuple[str, ...] = ()
    #: Geographic grain of the rows as published. 'precinct' rows are summed to
    #: county in the adapter — the CDM is county grain.
    grain: str = "county"
    #: Free-text note surfaced in the _manifest tab.
    note: str = ""
    #: True if certified by Georgia Secretary of State; False for provisional/uncertified.
    certified: bool = True


_MODES_STANDARD = (
    "election_day_votes",
    "advanced_votes",
    "absentee_by_mail_votes",
    "provisional_votes",
)

#: Registry keyed by cycle year. Order matters only for display.
SOURCES: dict[int, Source] = {
    2000: Source(
        source_id="oe_ga_20001107_general",
        election_date="2000-11-07", cycle_year=2000, election_type="general",
        patterns=("2000/20001107__ga__general.csv",),
        votes_total_column="votes", grain="county",
    ),
    2002: Source(
        source_id="oe_ga_20021105_general",
        election_date="2002-11-05", cycle_year=2002, election_type="general",
        patterns=("2002/20021105__ga__general.csv",),
        votes_total_column="votes", grain="county",
    ),
    2004: Source(
        source_id="oe_ga_20041102_general",
        election_date="2004-11-02", cycle_year=2004, election_type="general",
        patterns=("2004/20041102__ga__general.csv",),
        votes_total_column="votes", grain="county",
    ),
    2006: Source(
        source_id="oe_ga_20061107_general",
        election_date="2006-11-07", cycle_year=2006, election_type="general",
        patterns=("2006/20061107__ga__general.csv",),
        votes_total_column="votes", grain="county",
    ),
    2008: Source(
        source_id="oe_ga_20081104_general",
        election_date="2008-11-04", cycle_year=2008, election_type="general",
        patterns=("2008/20081104__ga__general.csv",),
        votes_total_column="votes", grain="county",
    ),
    2010: Source(
        source_id="oe_ga_20101102_general",
        election_date="2010-11-02", cycle_year=2010, election_type="general",
        patterns=("2010/20101102__ga__general.csv",),
        votes_total_column="votes", grain="county",
    ),
    2012: Source(
        source_id="oe_ga_20121106_general",
        election_date="2012-11-06", cycle_year=2012, election_type="general",
        patterns=("2012/20121106__ga__general.csv",),
        votes_mode_columns=_MODES_STANDARD, grain="precinct",
        note="Filename says 'general' but rows are precinct grain.",
    ),
    2014: Source(
        source_id="oe_ga_20141104_general",
        election_date="2014-11-04", cycle_year=2014, election_type="general",
        patterns=("2014/20141104__ga__general__county-level.csv",),
        votes_mode_columns=_MODES_STANDARD, grain="county",
    ),
    2016: Source(
        source_id="oe_ga_20161108_general",
        election_date="2016-11-08", cycle_year=2016, election_type="general",
        patterns=("2016/20161108__ga__general.csv",),
        votes_total_column="votes", grain="county",
        note="Office names use the long form ('State Representative'); "
             "~1.1k rows carry a stray-paren party artifact ('(REP').",
    ),
    2018: Source(
        source_id="oe_ga_20181106_general",
        election_date="2018-11-06", cycle_year=2018, election_type="general",
        patterns=("2018/20181106__ga__general__*__precinct.csv",),
        votes_total_column="votes", grain="precinct",
        note="Published as 159 per-county precinct files; no statewide file. "
             "~24k rows carry the stray-paren party artifact.",
    ),
    2020: Source(
        source_id="oe_ga_20201103_general",
        election_date="2020-11-03", cycle_year=2020, election_type="general",
        patterns=("2020/20201103__ga__general.csv",),
        votes_mode_columns=_MODES_STANDARD, grain="precinct",
        note="Includes 'U.S. Senate (Special)' — the Loeffler/Warnock seat.",
    ),
    2022: Source(
        source_id="oe_ga_20221108_general",
        election_date="2022-11-08", cycle_year=2022, election_type="general",
        patterns=("2022/20221108__ga__general__precinct.csv",),
        votes_mode_columns=_MODES_STANDARD, grain="precinct",
    ),
    2024: Source(
        source_id="oe_ga_20241105_general",
        election_date="2024-11-05", cycle_year=2024, election_type="general",
        patterns=("2024/20241105__ga__general__county-level.csv",),
        votes_mode_columns=_MODES_STANDARD, grain="county",
        certified=True,
    ),
    2026: Source(
        source_id="oe_ga_20261103_general",
        election_date="2026-11-03", cycle_year=2026, election_type="general",
        patterns=("2026/20261103__ga__general__county-level.csv",),
        votes_total_column="votes", grain="county",
        certified=False,
        note="⚠️ UNCERTIFIED: Pending Georgia Secretary of State certification. For development/testing only.",
    ),
}

#: Cycles in the analysis, ascending.
CYCLES: list[int] = sorted(SOURCES)
