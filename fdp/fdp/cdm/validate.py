"""
validate.py — Contract tests every build must pass.

The legacy workbook had no automated checks: its "Ballotpedia check" tab was
done by hand, once, in 2019, and the 2024 check was never done at all. Three
separate audits over six years each found a hardcoded value that had silently
replaced a formula. These checks are the replacement — they run on every build
and their results are published alongside the data as ``_validation``.

Severity
--------
  FAIL   a real defect; the build should not be published
  KNOWN  a documented source limitation with a recorded reason (see KNOWN_GAPS)
  WARN   worth a look, not blocking
  PASS   check succeeded
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .schema import CHAMBERS, CONGRESSIONAL_SEATS, OFFICES, PARTIES

GEORGIA_COUNTIES = 159


@dataclass(frozen=True)
class KnownGap:
    """A source limitation we have investigated and chosen to accept."""

    cycle_year: int
    office: str
    reason: str


#: Gaps confirmed against the raw source files and the legacy workbook.
#: Each one was verified to be a property of the published data, not of the
#: adapter. Anything not listed here that fails a check is a real FAIL.
KNOWN_GAPS: tuple[KnownGap, ...] = (
    KnownGap(
        2002, "state_house",
        "Georgia's 2001 House plan used multi-member districts: 147 districts "
        "elected 180 members. The source carries no post identifier, so seat "
        "winners are not derivable. Votes are complete and correct. The legacy "
        "workbook's 2002 tab also stops at district 147. (Plan later struck "
        "down in Larios v. Cox, 2004.)",
    ),
    KnownGap(
        2018, "state_house",
        "Districts 014 and 028 are absent from the OpenElections 2018 "
        "per-county precinct files. Verified absent in the raw source, not "
        "dropped by the adapter.",
    ),
)

_KNOWN_INDEX = {(g.cycle_year, g.office): g.reason for g in KNOWN_GAPS}

#: (cycle, chamber) pairs whose districts elect more than one member, so seat
#: attribution is not possible from district-level results alone.
MULTI_MEMBER: set[tuple[int, str]] = {(2002, "state_house")}


@dataclass
class Check:
    name: str
    severity: str          # PASS | WARN | KNOWN | FAIL
    scope: str             # e.g. '2018/state_house' or 'all'
    detail: str

    def as_row(self) -> dict:
        return {
            "check": self.name,
            "severity": self.severity,
            "scope": self.scope,
            "detail": self.detail,
        }


def _severity_for(cycle: int, office: str) -> tuple[str, str]:
    reason = _KNOWN_INDEX.get((cycle, office))
    return ("KNOWN", reason) if reason else ("FAIL", "")


def check_district_coverage(facts: pd.DataFrame) -> list[Check]:
    """Every (cycle, chamber) must carry its full complement of districts."""
    out: list[Check] = []
    for chamber in CHAMBERS:
        sub = facts[facts["office"] == chamber]
        for cycle, g in sub.groupby("cycle_year"):
            expected = (
                CONGRESSIONAL_SEATS.get(int(cycle))
                if OFFICES[chamber]["seats"] == "cd"
                else OFFICES[chamber]["seats"]
            )
            present = g["district"].nunique()
            scope = f"{int(cycle)}/{chamber}"
            if present == expected:
                out.append(Check("district_coverage", "PASS", scope,
                                 f"{present}/{expected} districts"))
            else:
                sev, reason = _severity_for(int(cycle), chamber)
                missing = sorted(
                    {f"{i:03d}" for i in range(1, (expected or 0) + 1)}
                    - set(g["district"].unique())
                )
                detail = f"{present}/{expected} districts; missing {missing[:8]}"
                if len(missing) > 8:
                    detail += f" (+{len(missing) - 8} more)"
                if reason:
                    detail += f" — {reason}"
                out.append(Check("district_coverage", sev, scope, detail))
    return out


def check_county_coverage(facts: pd.DataFrame) -> list[Check]:
    """Each cycle should cover all 159 Georgia counties."""
    out: list[Check] = []
    for cycle, g in facts.groupby("cycle_year"):
        counties = {c for c in g["county"].unique() if c and c != "Unknown"}
        n = len(counties)
        scope = f"{int(cycle)}/all"
        if n == GEORGIA_COUNTIES:
            out.append(Check("county_coverage", "PASS", scope, f"{n}/159 counties"))
        else:
            out.append(Check(
                "county_coverage", "FAIL" if n < GEORGIA_COUNTIES else "WARN",
                scope, f"{n}/159 counties",
            ))
    return out


def check_party_domain(facts: pd.DataFrame) -> list[Check]:
    """Every normalized party must be in the declared domain."""
    unknown = set(facts["party"].unique()) - set(PARTIES)
    if unknown:
        return [Check("party_domain", "FAIL", "all",
                      f"parties outside the declared domain: {sorted(unknown)}")]
    other = facts[facts["party"] == "O"]
    if len(other):
        sample = other["party_raw"].value_counts().head(5).to_dict()
        return [Check("party_domain", "WARN", "all",
                      f"{len(other):,} rows mapped to 'Other'; raw values: {sample}")]
    return [Check("party_domain", "PASS", "all",
                  f"all rows in {sorted(PARTIES)}")]


def check_votes_sane(facts: pd.DataFrame) -> list[Check]:
    """Votes must be non-negative integers with no nulls."""
    out: list[Check] = []
    nulls = int(facts["votes"].isna().sum())
    negatives = int((facts["votes"] < 0).sum())
    if nulls or negatives:
        out.append(Check("votes_sane", "FAIL", "all",
                         f"{nulls} null and {negatives} negative vote values"))
    else:
        out.append(Check("votes_sane", "PASS", "all",
                         f"{len(facts):,} rows, {int(facts['votes'].sum()):,} votes"))
    return out


def check_grain_unique(facts: pd.DataFrame) -> list[Check]:
    """The declared grain must actually be unique — no duplicate fact rows."""
    # election_type belongs in the key: two races for the same office can share
    # a date. In 2020 the regular U.S. Senate race and the Loeffler/Warnock
    # special were both held on 2020-11-03.
    keys = ["election_date", "election_type", "office", "district", "county",
            "candidate_name", "party"]
    dupes = int(facts.duplicated(subset=keys).sum())
    sev = "PASS" if dupes == 0 else "FAIL"
    return [Check("grain_unique", sev, "all",
                  f"{dupes} duplicate rows at grain {keys}")]


def check_contest_has_votes(contests: pd.DataFrame) -> list[Check]:
    """No contest should have zero total votes."""
    empty = contests[contests["votes_total"] <= 0]
    if len(empty):
        sample = empty[["cycle_year", "office", "district"]].head(5).to_dict("records")
        return [Check("contest_has_votes", "FAIL", "all",
                      f"{len(empty)} contests with no votes: {sample}")]
    return [Check("contest_has_votes", "PASS", "all",
                  f"all {len(contests):,} contests have votes")]


def check_seat_totals(chamber_year: pd.DataFrame) -> list[Check]:
    """Derived seat counts must sum to the chamber's size."""
    out: list[Check] = []
    for row in chamber_year.itertuples():
        scope = f"{row.cycle_year}/{row.chamber}"
        if not row.seats_derivable:
            reason = _KNOWN_INDEX.get((row.cycle_year, row.chamber), "")
            out.append(Check("seat_totals", "KNOWN", scope,
                             f"seat attribution not derivable — {reason}"))
            continue
        got = (row.seats_r or 0) + (row.seats_d or 0) + (row.seats_other or 0)
        expected = row.seats_total_expected
        if expected is not None and got != expected:
            sev, reason = _severity_for(int(row.cycle_year), row.chamber)
            detail = f"seats sum to {got}, expected {expected}"
            if reason:
                detail += f" — {reason}"
            out.append(Check("seat_totals", sev, scope, detail))
        else:
            out.append(Check("seat_totals", "PASS", scope,
                             f"{got} seats = {expected} expected"))
    return out


def check_votes_reconcile(facts: pd.DataFrame, contests: pd.DataFrame) -> list[Check]:
    """Aggregates must not lose or invent votes relative to the fact table."""
    fact_total = int(facts["votes"].sum())
    contest_total = int(contests["votes_total"].sum())
    if fact_total != contest_total:
        return [Check("votes_reconcile", "FAIL", "all",
                      f"facts {fact_total:,} != contests {contest_total:,} "
                      f"(delta {contest_total - fact_total:,})")]
    return [Check("votes_reconcile", "PASS", "all",
                  f"{fact_total:,} votes preserved through aggregation")]


def run_all(facts: pd.DataFrame,
            contests: pd.DataFrame,
            chamber_year: pd.DataFrame) -> pd.DataFrame:
    """Run every check and return the results as a publishable table."""
    checks: list[Check] = []
    checks += check_grain_unique(facts)
    checks += check_votes_sane(facts)
    checks += check_party_domain(facts)
    checks += check_county_coverage(facts)
    checks += check_district_coverage(facts)
    checks += check_contest_has_votes(contests)
    checks += check_votes_reconcile(facts, contests)
    checks += check_seat_totals(chamber_year)

    df = pd.DataFrame([c.as_row() for c in checks])
    order = {"FAIL": 0, "WARN": 1, "KNOWN": 2, "PASS": 3}
    return (
        df.assign(_o=df["severity"].map(order))
          .sort_values(["_o", "check", "scope"], kind="stable")
          .drop(columns="_o")
          .reset_index(drop=True)
    )


def summarize(validation: pd.DataFrame) -> str:
    counts = validation["severity"].value_counts().to_dict()
    return "  ".join(
        f"{s}={counts.get(s, 0)}" for s in ("FAIL", "WARN", "KNOWN", "PASS")
    )
