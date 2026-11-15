"""
corrections.py — Documented fixes for confirmed errors in the source data.

A canonical model over community-maintained sources needs somewhere to record
"this row is wrong, here is the evidence, here is the fix". That place is this
file, and nowhere else — adapters stay mechanical, and every correction carries
the evidence that justifies it.

Rules for adding one
--------------------
1. The error must be verified against an independent source. For everything
   below, that source is the legacy "Ga Gen Assembly Analysis" workbook, whose
   vote counts match the OpenElections rows exactly — only the label differs.
2. Record *why* in ``evidence``. A correction without evidence is a guess.
3. Corrections are matched, not blind. If a correction stops matching any row
   (because the upstream source was fixed), the build reports it rather than
   silently doing nothing — see ``apply`` and the ``rows_matched`` report.

Why these exist
---------------
The dominant OpenElections error for Georgia is misreading the incumbency
marker ``(I)`` in a candidate name as the party "Independent". The legacy
workbook writes incumbents as ``STACEY ABRAMS (I)`` with party ``(D)`` in a
separate column; the OpenElections import collapsed the two.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class Correction:
    """One documented fix. Match fields select rows; set fields change them."""

    cycle_year: int
    office: str
    evidence: str
    #: Match on these (None = do not constrain).
    district: str | None = None
    candidate_name: str | None = None
    party: str | None = None
    #: Apply these (None = leave unchanged).
    set_district: str | None = None
    set_candidate_name: str | None = None
    set_party: str | None = None

    def mask(self, df: pd.DataFrame) -> pd.Series:
        m = (df["cycle_year"] == self.cycle_year) & (df["office"] == self.office)
        if self.district is not None:
            m &= df["district"] == self.district
        if self.candidate_name is not None:
            m &= df["candidate_name"] == self.candidate_name
        if self.party is not None:
            m &= df["party"] == self.party
        return m

    @property
    def label(self) -> str:
        target = self.candidate_name or self.district or "*"
        changes = ", ".join(
            f"{k}->{v}" for k, v in (
                ("district", self.set_district),
                ("candidate_name", self.set_candidate_name),
                ("party", self.set_party),
            ) if v is not None
        )
        return f"{self.cycle_year}/{self.office}/{target}: {changes}"


_ABRAMS_EVIDENCE = (
    "OpenElections read the incumbency marker '(I)' in the candidate name as "
    "the party 'Independent'. The legacy workbook's 2012 tab lists this "
    "candidate with the same vote total and the party shown here in a "
    "separate column."
)

CORRECTIONS: tuple[Correction, ...] = (
    # ---- 2012: incumbency marker misread as party --------------------------
    Correction(2012, "state_house", _ABRAMS_EVIDENCE,
               district="089", candidate_name="STACEY ABRAMS", party="I",
               set_party="D"),
    Correction(2012, "state_house", _ABRAMS_EVIDENCE,
               district="087", candidate_name="EARNEST WILLIAMS", party="I",
               set_party="D"),
    Correction(2012, "state_house", _ABRAMS_EVIDENCE,
               district="125", candidate_name="EARNEST SMITH", party="I",
               set_party="D"),
    Correction(2012, "state_house", _ABRAMS_EVIDENCE,
               district="107", candidate_name="DAVID CASAS", party="I",
               set_party="R"),
    Correction(2012, "state_senate", _ABRAMS_EVIDENCE,
               district="022", candidate_name="HARDIE DAVIS", party="I",
               set_party="D"),

    # ---- 2012: one candidate spelled two ways, splitting the vote ----------
    Correction(
        2012, "state_house",
        "The same candidate appears as 'E. CULVER KIDD' (8,036) and "
        "'E.CULVER KIDD' (1,937) in district 145, splitting one candidate's "
        "vote across two rows. The workbook records a single row of 9,973 = "
        "8,036 + 1,937. Genuinely an Independent — the workbook writes "
        "'E. CULVER KIDD(I)(I)', i.e. incumbent and Independent.",
        district="145", candidate_name="E.CULVER KIDD",
        set_candidate_name="E. CULVER KIDD",
    ),

    # ---- 2022: candidate assigned to the wrong district ---------------------
    Correction(
        2022, "state_house",
        "Shaw Blackmon's rows are labeled district 145, but he represented "
        "district 146. In the raw source, district 145 holds two Republicans "
        "(Dickey 15,964 and Blackmon 15,956) while district 146 holds only an "
        "unopposed Democrat. The workbook places Blackmon in 146 with the "
        "identical 15,956 votes, opposed by Courtney L. Driver (8,937). "
        "Correcting this yields 101R/79D, matching the certified result.",
        district="145", candidate_name="Shaw Blackmon",
        set_district="146",
    ),
)


@dataclass
class CorrectionReport:
    label: str
    evidence: str
    rows_matched: int

    def as_row(self) -> dict:
        return {
            "correction": self.label,
            "rows_matched": self.rows_matched,
            "status": "APPLIED" if self.rows_matched else "NO_MATCH",
            "evidence": self.evidence,
        }


def apply(facts: pd.DataFrame,
          corrections: tuple[Correction, ...] = CORRECTIONS,
          ) -> tuple[pd.DataFrame, list[CorrectionReport]]:
    """Apply every correction and report how many rows each one touched.

    A correction matching zero rows is reported as NO_MATCH rather than being
    ignored — that usually means the upstream source has been fixed and the
    entry here should be retired.
    """
    df = facts.copy()
    reports: list[CorrectionReport] = []

    for c in corrections:
        m = c.mask(df)
        n = int(m.sum())
        if n:
            if c.set_party is not None:
                df.loc[m, "party"] = c.set_party
            if c.set_district is not None:
                df.loc[m, "district"] = c.set_district
            if c.set_candidate_name is not None:
                df.loc[m, "candidate_name"] = c.set_candidate_name
        reports.append(CorrectionReport(c.label, c.evidence, n))

    # A rename or district move can produce two rows that now share the fact
    # grain; re-aggregate so the declared grain stays unique.
    keys = [k for k in df.columns if k not in ("votes", "source_row")]
    df = (
        df.groupby(keys, as_index=False, dropna=False)
          .agg(votes=("votes", "sum"), source_row=("source_row", "min"))
    )
    return df[facts.columns], reports


# ---------------------------------------------------------------------------
# Candidate name canonicalization
# ---------------------------------------------------------------------------
# Several source files spell the same candidate differently *by county*, which
# splits one person's vote across two or more rows and corrupts every derived
# share. In the 2012 file Hank Johnson appears four ways in CD-4; Paul Broun
# two ways in CD-10; Lynn Westmoreland two ways in CD-3 (which is why the
# workbook records him as unopposed at 100% while the raw data shows 85.7%).
#
# The merge rule is deliberately conservative: two rows are the same candidate
# only when they share an election, an office, a district, a party *and* a
# surname. In a general election each party fields one nominee per district, so
# a same-party surname collision within one contest is a spelling variant
# rather than two people. Every merge is reported for audit.

_NAME_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}


def _surname(name: str) -> str:
    """Last name-bearing token, ignoring generational suffixes.

    Punctuation becomes whitespace first, so hyphenated surnames match across
    spellings ('D. D-HAIGLER' and 'D DAW-HAIGLER' both yield 'HAIGLER').
    """
    cleaned = re.sub(r"[^A-Za-z ]", " ", str(name).upper())
    tokens = [t for t in cleaned.split() if t and t not in _NAME_SUFFIXES]
    return tokens[-1] if tokens else ""


def canonicalize_names(facts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge candidate name variants within a contest. Returns (facts, report)."""
    df = facts.copy()
    df["_surname"] = df["candidate_name"].map(_surname)
    keys = ["cycle_year", "office", "district", "party", "_surname"]

    # Canonical spelling = the variant carrying the most votes; ties break on
    # the longer (more complete) name so 'PAUL C. BROUN' beats 'PAUL BROUN'
    # only if it also has more votes.
    totals = (
        df.groupby(keys + ["candidate_name"], as_index=False)["votes"].sum()
        .assign(_len=lambda d: d["candidate_name"].str.len())
        .sort_values(["votes", "_len"], ascending=[False, False], kind="stable")
    )
    canonical = totals.groupby(keys, as_index=False).first()[keys + ["candidate_name"]]
    canonical = canonical.rename(columns={"candidate_name": "_canonical"})

    variants = totals.groupby(keys, as_index=False)["candidate_name"].nunique()
    variants = variants.rename(columns={"candidate_name": "_variants"})

    df = df.merge(canonical, on=keys, how="left").merge(variants, on=keys, how="left")

    merged = df[(df["_variants"] > 1) & (df["candidate_name"] != df["_canonical"])]
    report = (
        merged.groupby(
            ["cycle_year", "office", "district", "party",
             "candidate_name", "_canonical"], as_index=False,
        )["votes"].sum()
        .rename(columns={"candidate_name": "merged_from",
                         "_canonical": "merged_into",
                         "votes": "votes_moved"})
        .sort_values(["cycle_year", "office", "district"], kind="stable")
        .reset_index(drop=True)
    )

    df["candidate_name"] = df["_canonical"].fillna(df["candidate_name"])
    df = df.drop(columns=["_surname", "_canonical", "_variants"])

    group_keys = [k for k in df.columns if k not in ("votes", "source_row")]
    df = (
        df.groupby(group_keys, as_index=False, dropna=False)
          .agg(votes=("votes", "sum"), source_row=("source_row", "min"))
    )
    return df[facts.columns], report
