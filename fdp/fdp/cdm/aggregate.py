"""
aggregate.py — Derive the two analysis tables from the CDM fact table.

    facts  ──► contests       one row per (election, office, district)
           └─► chamber_year   one row per (cycle_year, chamber)

Everything requiring a policy decision is applied *here*, in one place, rather
than being copied across thousands of spreadsheet formulas. The two decisions
that matter:

  uncontested  Two defensible definitions, so both are emitted and the caller
               chooses:

                 ``is_uncontested``        no opponent on the ballot, ignoring
                                           write-ins. Matches the legacy
                                           workbook's rule (``=IF(E=100,1,0)``)
                                           and is the default, so published
                                           history reconciles. Write-ins are
                                           excluded deliberately: in 2008 CD-5
                                           John Lewis drew 231,368 votes against
                                           two write-ins totalling 93, which no
                                           reading of "contested" should count.
                 ``is_uncontested_major``  no *major-party* opponent. A
                                           Republican facing only a Libertarian
                                           counts as uncontested. Arguably the
                                           better measure of an uncompetitive
                                           seat; it differs from the strict rule
                                           in 30-40 races across the 13 cycles.

  competitive  The winner's share of the total vote is at or below
               ``COMPETITIVE_LIMIT``. Materialized at several thresholds so the
               presentation layer can offer a selector with no recomputation.

Mechanical properties (winner, margin, vote totals) carry no policy and are
computed directly.

Multi-member districts
----------------------
Georgia's 2001 state House plan used multi-member districts — 147 districts
electing 180 members. The source carries no post identifier, so seat winners
are not derivable for that chamber-cycle. Rather than fabricate a number, the
affected rows carry ``seats_derivable = False`` and their seat columns are left
null; vote columns remain valid throughout.
"""

from __future__ import annotations

import pandas as pd

from .schema import (
    CHAMBERS,
    COMPETITIVE_LIMIT,
    COMPETITIVE_LIMITS,
    CONGRESSIONAL_SEATS,
    MAJOR_PARTIES,
    OFFICES,
)

CONTEST_COLUMNS = [
    "cycle_year", "election_date", "election_type", "office", "district",
    "candidate_count", "party_count",
    "winner_party", "winner_name", "winner_votes", "winner_share",
    "runner_up_party", "runner_up_votes",
    "margin", "margin_share",
    "votes_total", "votes_r", "votes_d", "votes_other",
    "counties", "is_uncontested", "is_uncontested_major", "is_competitive",
]

CHAMBER_YEAR_COLUMNS = [
    "cycle_year", "chamber",
    "seats_total_expected", "districts_present", "seats_derivable",
    "seats_r", "seats_d", "seats_other",
    "pct_seats_r", "pct_seats_d",
    "races_total", "races_uncontested", "races_contested", "races_competitive",
    "races_uncontested_major",
    "pct_uncontested", "pct_competitive",
    "votes_total", "votes_r", "votes_d", "votes_other",
    "pct_votes_r", "pct_votes_d",
    "seats_votes_gap_r",
]


def expected_seats(cycle_year: int, chamber: str) -> int | None:
    """Seats in a chamber for a given cycle, or None if unknown."""
    spec = OFFICES[chamber]["seats"]
    if spec == "cd":
        return CONGRESSIONAL_SEATS.get(cycle_year)
    return spec


def build_contests(facts: pd.DataFrame) -> pd.DataFrame:
    """Collapse candidate-county rows to one row per contest."""
    # Candidate totals across counties, within a contest.
    by_candidate = (
        facts.groupby(
            ["cycle_year", "election_date", "election_type", "office", "district",
             "candidate_name", "party"],
            as_index=False,
        )
        .agg(votes=("votes", "sum"), counties=("county", "nunique"))
        .sort_values("votes", ascending=False, kind="stable")
    )

    contest_keys = ["cycle_year", "election_date", "election_type", "office", "district"]
    grouped = by_candidate.groupby(contest_keys, as_index=False, sort=False)

    rows = []
    for key, g in grouped:
        g = g.sort_values("votes", ascending=False, kind="stable")
        total = int(g["votes"].sum())
        top = g.iloc[0]
        runner = g.iloc[1] if len(g) > 1 else None

        votes_r = int(g.loc[g["party"] == "R", "votes"].sum())
        votes_d = int(g.loc[g["party"] == "D", "votes"].sum())
        major_present = {p for p in g["party"].unique() if p in MAJOR_PARTIES}

        winner_share = (int(top["votes"]) / total) if total else float("nan")
        margin = int(top["votes"]) - (int(runner["votes"]) if runner is not None else 0)

        rows.append({
            "cycle_year": key[0], "election_date": key[1], "election_type": key[2],
            "office": key[3], "district": key[4],
            "candidate_count": len(g),
            "party_count": g["party"].nunique(),
            "winner_party": top["party"], "winner_name": top["candidate_name"],
            "winner_votes": int(top["votes"]), "winner_share": winner_share,
            "runner_up_party": runner["party"] if runner is not None else "",
            "runner_up_votes": int(runner["votes"]) if runner is not None else 0,
            "margin": margin,
            "margin_share": (margin / total) if total else float("nan"),
            "votes_total": total, "votes_r": votes_r, "votes_d": votes_d,
            "votes_other": total - votes_r - votes_d,
            "counties": int(g["counties"].max()),
            # Legacy-workbook rule: no opponent on the ballot, write-ins aside.
            "is_uncontested": int((g["party"] != "W").sum()) <= 1,
            # Broader rule: no major-party opponent.
            "is_uncontested_major": len(major_present) < 2,
        })

    contests = pd.DataFrame(rows)
    if contests.empty:
        return pd.DataFrame(columns=CONTEST_COLUMNS)

    # Policy: competitiveness at the default threshold, plus one boolean column
    # per alternate threshold so the UI can switch without recomputing.
    contests["is_competitive"] = (
        (~contests["is_uncontested"]) & (contests["winner_share"] <= COMPETITIVE_LIMIT)
    )
    for limit in COMPETITIVE_LIMITS:
        col = f"is_competitive_{str(limit).replace('.', '')}"
        contests[col] = (
            (~contests["is_uncontested"]) & (contests["winner_share"] <= limit)
        )

    extra = [c for c in contests.columns if c.startswith("is_competitive_")]
    ordered = CONTEST_COLUMNS + sorted(extra)
    return (
        contests[ordered]
        .sort_values(["cycle_year", "office", "district"], kind="stable")
        .reset_index(drop=True)
    )


def build_chamber_year(contests: pd.DataFrame,
                       multi_member: set[tuple[int, str]] | None = None) -> pd.DataFrame:
    """Roll contests up to one row per (cycle_year, chamber).

    ``multi_member`` holds (cycle_year, chamber) pairs whose districts elect
    more than one member. Seat columns are suppressed for those rows because
    the source carries no post identifier to attribute seats by.
    """
    multi_member = multi_member or set()
    chamber_contests = contests[contests["office"].isin(CHAMBERS)]

    rows = []
    for (cycle, chamber), g in chamber_contests.groupby(["cycle_year", "office"], sort=True):
        expected = expected_seats(int(cycle), chamber)
        derivable = (int(cycle), chamber) not in multi_member

        votes_total = int(g["votes_total"].sum())
        votes_r = int(g["votes_r"].sum())
        votes_d = int(g["votes_d"].sum())
        races_total = len(g)
        uncontested = int(g["is_uncontested"].sum())
        uncontested_major = int(g["is_uncontested_major"].sum())
        competitive = int(g["is_competitive"].sum())

        seats_r = seats_d = seats_other = None
        pct_seats_r = pct_seats_d = gap_r = None
        if derivable:
            seats_r = int((g["winner_party"] == "R").sum())
            seats_d = int((g["winner_party"] == "D").sum())
            seats_other = races_total - seats_r - seats_d
            if races_total:
                pct_seats_r = seats_r / races_total
                pct_seats_d = seats_d / races_total

        pct_votes_r = votes_r / votes_total if votes_total else None
        pct_votes_d = votes_d / votes_total if votes_total else None
        if pct_seats_r is not None and pct_votes_r is not None:
            gap_r = pct_seats_r - pct_votes_r

        rows.append({
            "cycle_year": int(cycle), "chamber": chamber,
            "seats_total_expected": expected,
            "districts_present": races_total,
            "seats_derivable": derivable,
            "seats_r": seats_r, "seats_d": seats_d, "seats_other": seats_other,
            "pct_seats_r": pct_seats_r, "pct_seats_d": pct_seats_d,
            "races_total": races_total,
            "races_uncontested": uncontested,
            "races_contested": races_total - uncontested,
            "races_competitive": competitive,
            "races_uncontested_major": uncontested_major,
            "pct_uncontested": uncontested / races_total if races_total else None,
            "pct_competitive": competitive / races_total if races_total else None,
            "votes_total": votes_total, "votes_r": votes_r, "votes_d": votes_d,
            "votes_other": votes_total - votes_r - votes_d,
            "pct_votes_r": pct_votes_r, "pct_votes_d": pct_votes_d,
            "seats_votes_gap_r": gap_r,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=CHAMBER_YEAR_COLUMNS)
    return (
        df[CHAMBER_YEAR_COLUMNS]
        .sort_values(["cycle_year", "chamber"], kind="stable")
        .reset_index(drop=True)
    )


def build_statewide(contests: pd.DataFrame) -> pd.DataFrame:
    """Statewide races (president / governor / US Senate) as vote-share rows.

    These drive the 'statewide vote proxy' comparison in the legacy workbook's
    Percentages tab — the baseline that chamber seat shares are measured against.
    """
    statewide = contests[~contests["office"].isin(CHAMBERS)].copy()
    if statewide.empty:
        return statewide
    statewide["pct_votes_r"] = statewide["votes_r"] / statewide["votes_total"]
    statewide["pct_votes_d"] = statewide["votes_d"] / statewide["votes_total"]
    cols = [
        "cycle_year", "election_date", "election_type", "office",
        "winner_party", "winner_name", "winner_share",
        "votes_total", "votes_r", "votes_d", "votes_other",
        "pct_votes_r", "pct_votes_d",
    ]
    return (
        statewide[cols]
        .sort_values(["cycle_year", "office"], kind="stable")
        .reset_index(drop=True)
    )
