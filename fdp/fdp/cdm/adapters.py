"""
adapters.py — Read raw source files and emit CDM ``facts`` rows.

This is the only module that touches source files. Everything downstream reads
the CDM. The per-cycle shape knowledge lives in ``sources.py``; this module
applies it.

What the adapter does, in order:
  1. Read every file matching the source's glob patterns (all columns as text,
     so nothing is silently retyped by the CSV reader).
  2. Resolve the vote total — either an explicit column or the sum of the
     vote-mode columns.
  3. Normalize office / party / district / candidate via ``schema``.
  4. Drop out-of-scope offices (ballot questions, PSC, AG, ...).
  5. Sum precinct rows up to county grain.

Rows are never silently dropped for being malformed: anything discarded is
counted and returned in an ``AdapterReport`` so the build surfaces it.
"""

from __future__ import annotations

import glob
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import schema
from .sources import Source

#: Grouping key for the county-grain fact table.
_GROUP_KEYS = [
    "election_date", "cycle_year", "election_type", "office", "district",
    "county", "candidate_name", "party_raw", "party",
]


@dataclass
class AdapterReport:
    """What one source produced, and what it discarded."""

    source_id: str
    cycle_year: int
    files_read: int
    rows_in: int
    rows_out: int
    dropped_out_of_scope: int = 0
    dropped_no_county: int = 0
    dropped_bad_votes: int = 0
    dropped_no_district: int = 0
    votes_total: int = 0
    offices_seen: list[str] = field(default_factory=list)
    offices_kept: list[str] = field(default_factory=list)
    unmapped_parties: dict[str, int] = field(default_factory=dict)
    reports_incumbency: bool = False
    file_sha256: str = ""

    def as_manifest_row(self, source: Source) -> dict:
        return {
            "source_id": self.source_id,
            "cycle_year": self.cycle_year,
            "election_date": source.election_date,
            "election_type": source.election_type,
            "grain_published": source.grain,
            "files_read": self.files_read,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "votes_total": self.votes_total,
            "dropped_out_of_scope": self.dropped_out_of_scope,
            "dropped_no_county": self.dropped_no_county,
            "dropped_bad_votes": self.dropped_bad_votes,
            "dropped_no_district": self.dropped_no_district,
            "offices_kept": ",".join(sorted(self.offices_kept)),
            "reports_incumbency": self.reports_incumbency,
            "unmapped_parties": ",".join(
                f"{k}({v})" for k, v in sorted(self.unmapped_parties.items())
            ),
            "sha256": self.file_sha256,
            "note": source.note,
        }


# Some sources carry votes that were never attributed to a county — the 2006
# file has 11 statewide write-in rows with county 'not available'. Those votes
# are real and belong in statewide totals, so they are kept under an explicit
# 'Unknown' sentinel rather than dropped; the county-coverage check ignores it.
_UNKNOWN_COUNTY_TOKENS = {"not available", "n/a", "na", "unknown", "none", ""}


def _normalize_county(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "Unknown"
    s = str(raw).strip()
    if s.lower() in _UNKNOWN_COUNTY_TOKENS:
        return "Unknown"
    return s.title()


def _resolve_files(root: Path, source: Source) -> list[Path]:
    files: list[Path] = []
    for pattern in source.patterns:
        matched = sorted(root.glob(pattern)) if any(c in pattern for c in "*?[") \
            else ([root / pattern] if (root / pattern).exists() else [])
        if not matched:
            raise FileNotFoundError(
                f"{source.source_id}: no file matched {pattern!r} under {root}"
            )
        files.extend(matched)
    return files


def _hash_files(files: list[Path]) -> str:
    """Stable digest over the byte content of every source file, in path order."""
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _resolve_votes(df: pd.DataFrame, source: Source) -> pd.Series:
    """Return an integer vote Series, from a total column or summed modes."""
    if source.votes_total_column:
        col = source.votes_total_column
        if col not in df.columns:
            raise KeyError(
                f"{source.source_id}: expected total column {col!r}; "
                f"file has {list(df.columns)}"
            )
        raw = df[col]
    else:
        missing = [c for c in source.votes_mode_columns if c not in df.columns]
        if missing:
            raise KeyError(
                f"{source.source_id}: missing vote-mode columns {missing}; "
                f"file has {list(df.columns)}"
            )
        raw = None
        for c in source.votes_mode_columns:
            part = pd.to_numeric(
                df[c].astype("string").str.replace(",", "", regex=False),
                errors="coerce",
            )
            raw = part if raw is None else raw.add(part, fill_value=0)
        return raw

    # Vote counts arrive as text with thousands separators in several vintages.
    return pd.to_numeric(
        raw.astype("string").str.replace(",", "", regex=False), errors="coerce"
    )


def load_source(root: Path, source: Source) -> tuple[pd.DataFrame, AdapterReport]:
    """Read one registry entry and return (facts, report)."""
    files = _resolve_files(root, source)
    frames = [pd.read_csv(f, dtype=str, low_memory=False) for f in files]
    raw = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    report = AdapterReport(
        source_id=source.source_id,
        cycle_year=source.cycle_year,
        files_read=len(files),
        rows_in=len(raw),
        rows_out=0,
        file_sha256=_hash_files(files),
    )
    report.offices_seen = sorted(raw["office"].dropna().unique().tolist())

    df = pd.DataFrame(index=raw.index)
    df["source_row"] = range(len(raw))
    df["office"] = raw["office"].map(schema.normalize_office)
    df["election_type"] = (
        raw["office"].map(schema.is_special_seat)
        .map({True: "special", False: source.election_type})
    )

    # Out-of-scope offices: ballot questions, PSC, AG, DA, Lt. Governor, ...
    in_scope = df["office"].notna()
    report.dropped_out_of_scope = int((~in_scope).sum())
    df, raw = df[in_scope].copy(), raw[in_scope].copy()
    report.offices_kept = sorted(df["office"].unique().tolist())

    df["election_date"] = source.election_date
    df["cycle_year"] = source.cycle_year
    df["county"] = raw["county"].map(_normalize_county)
    df["candidate_name"] = raw["candidate"].map(schema.normalize_candidate)
    df["party_raw"] = raw["party"].astype("string").fillna("")
    df["party"] = df["party_raw"].map(schema.normalize_party)
    df["district"] = [
        schema.normalize_district(d, o)
        for d, o in zip(raw.get("district", pd.Series(index=raw.index, dtype="string")),
                        df["office"])
    ]
    df["votes"] = _resolve_votes(raw, source)
    df["source_id"] = source.source_id

    # Track raw party strings that fell through to 'Other' so a genuinely new
    # party is a deliberate addition rather than a silent bucket.
    unmapped = df.loc[df["party"] == "O", "party_raw"]
    report.unmapped_parties = {
        str(k): int(v) for k, v in unmapped.value_counts().head(20).items()
    }

    # Incumbency is only meaningful if the source marks it anywhere at all.
    report.reports_incumbency = bool(
        df["candidate_name"].map(schema.detect_incumbent).any()
    )

    before = len(df)
    df = df[df["county"].notna() & (df["county"] != "")]
    report.dropped_no_county = before - len(df)

    before = len(df)
    df = df[df["votes"].notna()]
    report.dropped_bad_votes = before - len(df)
    df["votes"] = df["votes"].astype("int64")

    # A districted office with no district number cannot be assigned to a seat.
    districted = df["office"].map(lambda o: schema.OFFICES[o]["districted"])
    bad_district = districted & (df["district"] == "")
    report.dropped_no_district = int(bad_district.sum())
    df = df[~bad_district]

    # Published precinct rows roll up to county — the CDM is county grain.
    facts = (
        df.groupby(_GROUP_KEYS, as_index=False, dropna=False)
          .agg(votes=("votes", "sum"), source_row=("source_row", "min"))
    )
    facts["source_id"] = source.source_id
    facts = facts[schema.FACT_COLUMNS]

    report.rows_out = len(facts)
    report.votes_total = int(facts["votes"].sum())
    return facts, report


def load_all(root: Path, sources: dict[int, Source]) -> tuple[pd.DataFrame, list[AdapterReport]]:
    """Run every registry entry and concatenate into one fact table."""
    frames, reports = [], []
    for cycle in sorted(sources):
        facts, report = load_source(root, sources[cycle])
        frames.append(facts)
        reports.append(report)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(
        ["cycle_year", "office", "district", "county", "candidate_name"],
        kind="stable",
    ).reset_index(drop=True)
    return combined, reports
