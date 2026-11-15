#!/usr/bin/env python3
"""
build_fdga_cdm.py — Build the Georgia General Assembly canonical data model.

Replaces the manual "Ga Gen Assembly Analysis" Excel workbook, which carried
75,668 formulas across 13 per-year tabs to produce roughly 500 numbers. Each
year's tab had a different column layout, party encoding and percent scale, so
the same business rule was re-implemented every cycle — and several copies had
silently drifted.

Here the shape knowledge lives in ``fdp/cdm/sources.py`` (one entry per source
vintage), the business rules live once in ``fdp/cdm/aggregate.py``, and every
build is checked by ``fdp/cdm/validate.py``.

Layers
------
    raw OpenElections CSVs
        -> facts          county x contest x candidate   (no formulas, no judgments)
        -> contests       election x office x district    (mechanical properties)
        -> chamber_year   cycle x chamber                 (seats vs votes)
        -> statewide      cycle x statewide office        (the vote baseline)
        + _manifest       provenance: source, checksum, row counts
        + _validation     contract-test results

Outputs land in ``fdp/data/repos/main/fdga/`` as both Parquet (analytics, joins
to the rest of the platform) and CSV (Sheets, Power BI, Tableau).

Usage (from fgdp/ root):
    uv run --project fdp python fdp/scripts/build_fdga_cdm.py --fetch
    uv run --project fdp python fdp/scripts/build_fdga_cdm.py
    uv run --project fdp python fdp/scripts/build_fdga_cdm.py --cycle 2024
    uv run --project fdp python fdp/scripts/build_fdga_cdm.py --dry-run
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parent))

from fdp.cdm import adapters, aggregate, corrections, validate     # noqa: E402
from fdp.cdm.sources import SOURCES                                # noqa: E402

_FDP_ROOT = _SCRIPT_DIR.parent
_RAW_DIR = _FDP_ROOT / "data" / "raw" / "openelections"
_OE_ROOT = _RAW_DIR / "openelections-data-ga-master"
_OUT_DIR = _FDP_ROOT / "data" / "repos" / "main" / "fdga"

_TARBALL_URL = (
    "https://codeload.github.com/openelections/openelections-data-ga/"
    "tar.gz/refs/heads/master"
)


def fetch_sources(force: bool = False) -> None:
    """Download and unpack the OpenElections Georgia repository."""
    if _OE_ROOT.exists() and not force:
        print(f"Source already present: {_OE_ROOT}")
        print("  (pass --fetch --force to re-download)")
        return
    if _OE_ROOT.exists():
        shutil.rmtree(_OE_ROOT)
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {_TARBALL_URL} …")
    with urllib.request.urlopen(_TARBALL_URL) as resp:      # noqa: S310
        payload = resp.read()
    print(f"  {len(payload) / 1e6:.1f} MB — unpacking")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        tar.extractall(_RAW_DIR, filter="data")
    print(f"  -> {_OE_ROOT}")


def build(cycles: list[int] | None = None) -> dict[str, pd.DataFrame]:
    """Run the whole pipeline and return every output table."""
    selected = {c: s for c, s in SOURCES.items() if not cycles or c in cycles}
    if not selected:
        raise SystemExit(f"No sources match cycles {cycles}")

    print(f"Reading {len(selected)} source(s) from {_OE_ROOT}")
    facts, reports = adapters.load_all(_OE_ROOT, selected)
    print(f"  facts: {len(facts):,} rows, {int(facts['votes'].sum()):,} votes\n")

    manifest = pd.DataFrame(
        [r.as_manifest_row(selected[r.cycle_year]) for r in reports]
    )
    manifest["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print("Applying documented source corrections …")
    facts, correction_reports = corrections.apply(facts)
    applied = sum(1 for r in correction_reports if r.rows_matched)
    touched = sum(r.rows_matched for r in correction_reports)
    print(f"  {applied}/{len(correction_reports)} corrections matched, "
          f"{touched:,} rows touched")
    for r in correction_reports:
        if not r.rows_matched:
            print(f"  ! NO MATCH — {r.label} "
                  f"(source may have been fixed upstream; review this entry)")
    corrections_table = pd.DataFrame([r.as_row() for r in correction_reports])

    facts, merges = corrections.canonicalize_names(facts)
    print(f"  merged {len(merges)} candidate name variant(s) "
          f"({int(merges['votes_moved'].sum()):,} votes reunited) "
          f"across {merges['cycle_year'].nunique() if len(merges) else 0} cycle(s)")
    print()

    print("Building aggregates …")
    contests = aggregate.build_contests(facts)
    chamber_year = aggregate.build_chamber_year(contests, validate.MULTI_MEMBER)
    statewide = aggregate.build_statewide(contests)
    print(f"  contests:     {len(contests):,} rows")
    print(f"  chamber_year: {len(chamber_year):,} rows")
    print(f"  statewide:    {len(statewide):,} rows\n")

    print("Validating …")
    validation = validate.run_all(facts, contests, chamber_year)
    print(f"  {validate.summarize(validation)}\n")

    return {
        "facts": facts,
        "contests": contests,
        "chamber_year": chamber_year,
        "statewide": statewide,
        "_manifest": manifest,
        "_corrections": corrections_table,
        "_name_merges": merges,
        "_validation": validation,
    }


def write(tables: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing to {out_dir}")
    for name, df in tables.items():
        stem = name.lstrip("_")
        csv_path = out_dir / f"{stem}.csv"
        df.to_csv(csv_path, index=False)
        size = csv_path.stat().st_size
        line = f"  {name:14s} {len(df):7,d} rows  csv {size / 1024:8.1f} KB"
        # Meta tables stay CSV-only; the data tables also get Parquet for
        # platform joins and any BI tool that prefers a typed columnar file.
        if not name.startswith("_"):
            pq_path = out_dir / f"{stem}.parquet"
            df.to_parquet(pq_path, index=False, compression="zstd")
            line += f"  parquet {pq_path.stat().st_size / 1024:7.1f} KB"
        print(line)


def report(tables: dict[str, pd.DataFrame], verbose: bool) -> int:
    """Print the validation summary. Returns a process exit code."""
    validation = tables["_validation"]
    problems = validation[validation["severity"].isin(["FAIL", "WARN", "KNOWN"])]

    if len(problems):
        print("\nValidation findings")
        print("-" * 78)
        for row in problems.itertuples():
            detail = row.detail if verbose else row.detail[:150]
            print(f"  [{row.severity:5s}] {row.check:20s} {row.scope:22s} {detail}")

    cy = tables["chamber_year"]
    print("\nSeats vs. votes")
    print("-" * 78)
    print(f"{'cycle':>5} {'chamber':>13} {'seats R/D':>11} {'%seats R':>9} "
          f"{'%votes R':>9} {'gap':>7} {'uncont':>7} {'compet':>7}")
    for r in cy.itertuples():
        seats = f"{r.seats_r}/{r.seats_d}" if r.seats_derivable else "n/a"
        pct_s = f"{r.pct_seats_r:.1%}" if r.pct_seats_r is not None else "n/a"
        pct_v = f"{r.pct_votes_r:.1%}" if r.pct_votes_r is not None else "n/a"
        gap = f"{r.seats_votes_gap_r:+.1%}" if r.seats_votes_gap_r is not None else "n/a"
        print(f"{r.cycle_year:5d} {r.chamber:>13} {seats:>11} {pct_s:>9} {pct_v:>9} "
              f"{gap:>7} {r.races_uncontested:7d} {r.races_competitive:7d}")

    n_fail = int((validation["severity"] == "FAIL").sum())
    if n_fail:
        print(f"\n{n_fail} FAIL check(s) — do not publish this build.")
        return 1
    print("\nNo FAIL checks.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fetch", action="store_true",
                   help="download the OpenElections source repository first")
    p.add_argument("--force", action="store_true",
                   help="with --fetch, re-download even if already present")
    p.add_argument("--cycle", type=int, action="append", dest="cycles",
                   help="limit to one election cycle (repeatable)")
    p.add_argument("--out", type=Path, default=_OUT_DIR, help="output directory")
    p.add_argument("--dry-run", action="store_true",
                   help="build and validate but write nothing")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="print full validation detail text")
    args = p.parse_args()

    if args.fetch:
        fetch_sources(force=args.force)
    if not _OE_ROOT.exists():
        raise SystemExit(
            f"Source data not found at {_OE_ROOT}\n"
            "  Run with --fetch to download it."
        )

    tables = build(args.cycles)
    if args.dry_run:
        print("(--dry-run: nothing written)")
    else:
        write(tables, args.out)
    return report(tables, args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
