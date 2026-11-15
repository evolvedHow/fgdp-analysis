#!/usr/bin/env python3
"""
load_fdga_to_postgres.py — Publish the FDGA canonical data model to PostgreSQL.

This is the second of two sinks. Neither is downstream of the other:

    build_fdga_cdm.py  ──┬──►  PostgreSQL  ──►  Metabase   (analysts, live)
                         └──►  Google Sheets ─►  add-on     (spreadsheet users)

Both are outputs of the same validated build, so they cannot drift apart.

What this does NOT touch
------------------------
The apps — fdex, lrdb, map-compare, fdensemble — read static Parquet/GeoJSON
copied by `fdp sync-app` and deploy to GitHub Pages. They have no database
dependency and this script introduces none. If Postgres is down, every public
map still works.

Reload semantics
----------------
The whole dataset is replaced inside a single transaction: TRUNCATE, then COPY,
then COMMIT. Readers see the old data until the commit and the new data after —
never a half-loaded state, and never an empty table. If any step fails the
transaction rolls back and the previous load survives intact.

Usage (from fgdp/ root):
    export FDGA_DATABASE_URL=postgresql://user:pass@host:5432/dbname
    uv run --project fdp python fdp/scripts/load_fdga_to_postgres.py
    uv run --project fdp python fdp/scripts/load_fdga_to_postgres.py --dry-run
    uv run --project fdp python fdp/scripts/load_fdga_to_postgres.py --grant-read-only metabase_ro
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from pathlib import Path

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parent))

_FDP_ROOT = _SCRIPT_DIR.parent
_FDGA_DIR = _FDP_ROOT / "data" / "repos" / "main" / "fdga"
_DDL_PATH = _FDP_ROOT / "fdp" / "cdm" / "postgres_ddl.sql"
_COMMENTS_PATH = _FDP_ROOT / "fdp" / "cdm" / "postgres_comments.sql"

SCHEMA = "fdga"

#: Load order matters: facts carries a foreign key into manifest.
#: table -> (csv stem, [columns in DDL order])
TABLES: dict[str, tuple[str, list[str]]] = {
    "manifest": ("manifest", [
        "source_id", "cycle_year", "election_date", "election_type",
        "grain_published", "files_read", "rows_in", "rows_out", "votes_total",
        "dropped_out_of_scope", "dropped_no_county", "dropped_bad_votes",
        "dropped_no_district", "offices_kept", "reports_incumbency",
        "unmapped_parties", "sha256", "note", "built_at",
    ]),
    "facts": ("facts", [
        "election_date", "cycle_year", "election_type", "office", "district",
        "county", "candidate_name", "party_raw", "party", "votes",
        "source_id", "source_row",
    ]),
    "contests": ("contests", [
        "cycle_year", "election_date", "election_type", "office", "district",
        "candidate_count", "party_count", "winner_party", "winner_name",
        "winner_votes", "winner_share", "runner_up_party", "runner_up_votes",
        "margin", "margin_share", "votes_total", "votes_r", "votes_d",
        "votes_other", "counties", "is_uncontested", "is_uncontested_major",
        "is_competitive", "is_competitive_052", "is_competitive_0535",
        "is_competitive_055", "is_competitive_06",
    ]),
    "chamber_year": ("chamber_year", [
        "cycle_year", "chamber", "seats_total_expected", "districts_present",
        "seats_derivable", "seats_r", "seats_d", "seats_other", "pct_seats_r",
        "pct_seats_d", "races_total", "races_uncontested", "races_contested",
        "races_competitive", "races_uncontested_major", "pct_uncontested",
        "pct_competitive", "votes_total", "votes_r", "votes_d", "votes_other",
        "pct_votes_r", "pct_votes_d", "seats_votes_gap_r",
    ]),
    "statewide": ("statewide", [
        "cycle_year", "election_date", "election_type", "office",
        "winner_party", "winner_name", "winner_share", "votes_total",
        "votes_r", "votes_d", "votes_other", "pct_votes_r", "pct_votes_d",
    ]),
    "corrections": ("corrections", [
        "correction", "rows_matched", "status", "evidence",
    ]),
    "name_merges": ("name_merges", [
        "cycle_year", "office", "district", "party", "merged_from",
        "merged_into", "votes_moved",
    ]),
    # 'check' is reserved in SQL, so the column is check_name in the DDL.
    "validation": ("validation", [
        "check_name", "severity", "scope", "detail",
    ]),
    "reconciliation": ("reconciliation", [
        "cycle_year", "chamber", "field", "cdm", "workbook", "delta", "status",
    ]),
}

#: CSV header -> DDL column, where they differ.
_RENAMES = {"validation": {"check": "check_name"}}

#: Columns that must stay text even though they look numeric. Zero-padded
#: district numbers lose their padding if pandas infers them as integers, which
#: silently breaks every join between facts and contests.
_TEXT_COLUMNS = {"district"}

#: NOT NULL text columns where the CDM uses an empty string to mean "not
#: applicable" — statewide races have no district. pandas reads an empty CSV
#: field as NaN even under dtype=str, so it is restored to '' before COPY.
_EMPTY_STRING_COLUMNS = {"district"}

#: COPY's NULL marker. Deliberately not the empty string: '' is a *value* for
#: district (statewide races), while a blank numeric like seats_r for 2002 is a
#: genuine NULL. Using '' for both conflates them and trips the NOT NULL
#: constraint on district.
_NULL_SENTINEL = r"\N"


def read_table(name: str, columns: list[str], fdga_dir: Path) -> pd.DataFrame:
    stem = TABLES[name][0]
    path = fdga_dir / f"{stem}.csv"
    if not path.exists():
        raise SystemExit(
            f"{path} not found — run build_fdga_cdm.py first."
        )
    df = pd.read_csv(path, dtype={c: str for c in _TEXT_COLUMNS})
    df = df.rename(columns=_RENAMES.get(name, {}))

    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise SystemExit(
            f"{stem}.csv is missing column(s) {missing}. The build output and "
            f"the DDL have diverged — check fdp/cdm/postgres_ddl.sql."
        )
    df = df[columns].copy()
    for column in _EMPTY_STRING_COLUMNS & set(df.columns):
        df[column] = df[column].fillna("")
    return _restore_integers(df)


def _restore_integers(df: pd.DataFrame) -> pd.DataFrame:
    """Re-integerize float columns that only hold whole numbers.

    A nullable integer column round-trips through CSV as float64 — 2002's NULL
    seat counts turn every seats_* value into '74.0', which Postgres rejects
    for an integer column. pandas' nullable Int64 preserves the NULL and
    serializes as '74'.

    Columns with genuine fractional values (the pct_* family) are left alone.
    A float column that happens to hold only whole numbers is converted too,
    which is harmless: Postgres accepts '1' for double precision.
    """
    for column in df.columns:
        if df[column].dtype.kind != "f":
            continue
        values = df[column].dropna()
        if values.empty or (values % 1 == 0).all():
            df[column] = df[column].astype("Int64")
    return df


def to_copy_buffer(df: pd.DataFrame) -> io.StringIO:
    """Serialize to CSV for COPY, distinguishing empty string from NULL."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep=_NULL_SENTINEL,
              quoting=csv.QUOTE_MINIMAL)
    buf.seek(0)
    return buf


def apply_comments(database_url: str) -> int:
    """Apply table/view/column documentation, without touching any data.

    Metabase reads PostgreSQL COMMENT text over JDBC and uses it as the initial
    table and field description — but only populates a description that is
    currently empty (metabase#38694). Run this BEFORE connecting the database
    to Metabase. If it is already connected and descriptions are set, clear
    them in Admin > Table Metadata and re-sync for changes here to appear.
    """
    try:
        import psycopg
    except ImportError:
        raise SystemExit(
            "psycopg is required:\n  uv add --project fdp 'psycopg[binary]'")

    sql = _COMMENTS_PATH.read_text()
    print(f"Applying {_COMMENTS_PATH.name} "
          f"({sql.count('COMMENT ON')} COMMENT statements)")
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT c.relkind,
                       count(*) FILTER (WHERE obj_description(c.oid) IS NOT NULL),
                       count(*)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = '{SCHEMA}' AND c.relkind IN ('r', 'v')
                GROUP BY 1 ORDER BY 1
            """)
            for kind, documented, total in cur.fetchall():
                label = "tables" if kind == "r" else "views"
                print(f"  {label:7s} documented {documented}/{total}")

            cur.execute(f"""
                SELECT count(*) FILTER (
                           WHERE col_description(a.attrelid, a.attnum) IS NOT NULL),
                       count(*)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = '{SCHEMA}' AND c.relkind IN ('r', 'v')
                  AND a.attnum > 0 AND NOT a.attisdropped
            """)
            documented, total = cur.fetchone()
            print(f"  columns documented {documented}/{total}")
            if documented < total:
                cur.execute(f"""
                    SELECT c.relname, a.attname
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = '{SCHEMA}' AND c.relkind IN ('r', 'v')
                      AND a.attnum > 0 AND NOT a.attisdropped
                      AND col_description(a.attrelid, a.attnum) IS NULL
                    ORDER BY 1, 2
                """)
                print("\n  Undocumented columns:")
                for table, column in cur.fetchall():
                    print(f"    {table}.{column}")
    return 0


def load(database_url: str, fdga_dir: Path, grant_read_only: str | None,
         dry_run: bool) -> int:
    frames: dict[str, pd.DataFrame] = {}
    for name, (_stem, columns) in TABLES.items():
        frames[name] = read_table(name, columns, fdga_dir)

    print(f"Read {len(frames)} table(s) from {fdga_dir}")
    for name, df in frames.items():
        print(f"  {SCHEMA}.{name:16s} {len(df):7,d} rows x {len(df.columns):2d} cols")

    if dry_run:
        print("\n(--dry-run: nothing sent to the database)")
        return 0

    try:
        import psycopg
    except ImportError:
        raise SystemExit(
            "psycopg is required:\n"
            "  uv add --project fdp 'psycopg[binary]'"
        )

    ddl = _DDL_PATH.read_text()

    print(f"\nConnecting to {database_url.split('@')[-1]}")
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            print("Applying DDL (idempotent) …")
            cur.execute(ddl)
            print("Applying column documentation …")
            cur.execute(_COMMENTS_PATH.read_text())

            # One transaction for the whole reload: readers see the previous
            # data until COMMIT, then the new data. Never a partial state.
            # CASCADE is needed because facts references manifest.
            print("Reloading, atomically …")
            targets = ", ".join(f"{SCHEMA}.{t}" for t in TABLES)
            cur.execute(f"TRUNCATE {targets} CASCADE")

            for name, df in frames.items():
                columns = ", ".join(f'"{c}"' for c in df.columns)
                stmt = (
                    f"COPY {SCHEMA}.{name} ({columns}) "
                    f"FROM STDIN WITH (FORMAT csv, NULL '{_NULL_SENTINEL}')"
                )
                with cur.copy(stmt) as copy:
                    copy.write(to_copy_buffer(df).read())
                print(f"  {SCHEMA}.{name:16s} {len(df):7,d} rows")

            if grant_read_only:
                print(f"\nGranting read-only access to {grant_read_only!r} …")
                cur.execute(
                    f"GRANT USAGE ON SCHEMA {SCHEMA} TO {grant_read_only}")
                cur.execute(
                    f"GRANT SELECT ON ALL TABLES IN SCHEMA {SCHEMA} "
                    f"TO {grant_read_only}")
                cur.execute(
                    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
                    f"GRANT SELECT ON TABLES TO {grant_read_only}")

        conn.commit()
        print("\nCommitted.")

        # Read back through the health view rather than trusting the writes.
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {SCHEMA}.v_data_health")
            row = cur.fetchone()
            names = [d.name for d in cur.description]
            health = dict(zip(names, row))

    print("\nData health (read back from the database)")
    print("-" * 56)
    for key in ("failing_checks", "warnings", "known_gaps", "passing_checks",
                "corrections_applied", "name_variants_merged",
                "workbook_cells_matching", "workbook_cells_compared",
                "total_votes_loaded", "last_built_at"):
        value = health.get(key)
        shown = f"{value:,}" if isinstance(value, int) else value
        print(f"  {key:26s} {shown}")

    if health.get("failing_checks"):
        print(f"\n{health['failing_checks']} FAIL check(s) present in this load.")
        return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database-url",
                   default=os.environ.get("FDGA_DATABASE_URL")
                   or os.environ.get("DATABASE_URL"),
                   help="Postgres connection string "
                        "(default: $FDGA_DATABASE_URL, then $DATABASE_URL)")
    p.add_argument("--fdga-dir", type=Path, default=_FDGA_DIR)
    p.add_argument("--grant-read-only", metavar="ROLE",
                   help="grant SELECT on the schema to this existing role, "
                        "e.g. the role Metabase connects as")
    p.add_argument("--comments-only", action="store_true",
                   help="apply table/column documentation and exit, without "
                        "reloading any data")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would be loaded without connecting")
    args = p.parse_args()

    if not args.dry_run and not args.database_url:
        raise SystemExit(
            "Set FDGA_DATABASE_URL (or DATABASE_URL), or pass --database-url.")

    if args.comments_only:
        return apply_comments(args.database_url)

    return load(args.database_url or "", args.fdga_dir,
                args.grant_read_only, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
