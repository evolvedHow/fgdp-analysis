#!/usr/bin/env python3
"""
reconcile_fdga_workbook.py — Compare the CDM against the legacy Excel workbook.

This is the acceptance test for the migration. The new pipeline must reproduce
the numbers the "Ga Gen Assembly Analysis" workbook has been publishing, or
every difference must be explained. Where they disagree, one of the two is
wrong — and the workbook has a documented history of copy-paste defects, so a
difference is not automatically a bug in the CDM.

The workbook's per-year tabs carry a summary block whose row offsets drift:
rows 5/6/7 hold US House / GA Senate / GA House in every tab except 2022, where
the block starts one row higher. Columns are stable:

    G = GOP seats   H = Dem seats     I = Ind seats
    J = uncontested K = competitive   L = seat total

Usage (from fgdp/ root):
    uv run --project fdp python fdp/scripts/reconcile_fdga_workbook.py
    uv run --project fdp python fdp/scripts/reconcile_fdga_workbook.py --workbook path/to.xlsx
    uv run --project fdp python fdp/scripts/reconcile_fdga_workbook.py --csv out.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parent))

_FDP_ROOT = _SCRIPT_DIR.parent
_FDGA_DIR = _FDP_ROOT / "data" / "repos" / "main" / "fdga"
_DEFAULT_WORKBOOK = (
    _FDP_ROOT.parent / "Ga Gen Assembly Analysis (25-02-11).xlsx"
)

#: Workbook tab -> row offset of the summary block. Every tab uses rows 5/6/7
#: for US House / GA Senate / GA House except 2022, which starts a row higher.
_ROW_OFFSET = {"2022": -1}

#: Workbook summary-block row -> CDM chamber.
_CHAMBER_ROWS = {5: "us_house", 6: "state_senate", 7: "state_house"}

#: Workbook column -> the chamber_year field it should equal.
_FIELD_COLUMNS = {
    "seats_r": 7,           # G
    "seats_d": 8,           # H
    "races_uncontested": 10,  # J
    "races_competitive": 11,  # K
}


def read_workbook(path: Path) -> pd.DataFrame:
    """Extract the per-year summary blocks from every year tab."""
    try:
        import openpyxl
    except ImportError:  # pragma: no cover
        raise SystemExit(
            "openpyxl is required to read the legacy workbook.\n"
            "  uv add --project fdp openpyxl"
        )

    wb = openpyxl.load_workbook(path, data_only=True)
    rows = []
    for tab in wb.sheetnames:
        if not (tab.isdigit() and len(tab) == 4):
            continue
        ws = wb[tab]
        offset = _ROW_OFFSET.get(tab, 0)
        for row, chamber in _CHAMBER_ROWS.items():
            rec = {"cycle_year": int(tab), "chamber": chamber}
            for field, col in _FIELD_COLUMNS.items():
                value = ws.cell(row=row + offset, column=col).value
                rec[field] = None if value is None else value
            rows.append(rec)
    return pd.DataFrame(rows)


def reconcile(cdm: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    merged = cdm.merge(
        book, on=["cycle_year", "chamber"], how="outer",
        suffixes=("_cdm", "_book"),
    )
    out = []
    for row in merged.itertuples():
        for field in _FIELD_COLUMNS:
            got = getattr(row, f"{field}_cdm", None)
            want = getattr(row, f"{field}_book", None)
            got = None if pd.isna(got) else int(got)
            want = None if want is None or pd.isna(want) else int(want)
            if got is None and want is None:
                status, delta = "BOTH_NULL", None
            elif got is None:
                status, delta = "CDM_NULL", None
            elif want is None:
                status, delta = "BOOK_NULL", None
            elif got == want:
                status, delta = "MATCH", 0
            else:
                status, delta = "DIFF", got - want
            out.append({
                "cycle_year": row.cycle_year, "chamber": row.chamber,
                "field": field, "cdm": got, "workbook": want,
                "delta": delta, "status": status,
            })
    df = pd.DataFrame(out)
    order = {"DIFF": 0, "CDM_NULL": 1, "BOOK_NULL": 2, "BOTH_NULL": 3, "MATCH": 4}
    return (
        df.assign(_o=df["status"].map(order))
          .sort_values(["_o", "cycle_year", "chamber", "field"], kind="stable")
          .drop(columns="_o")
          .reset_index(drop=True)
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workbook", type=Path, default=_DEFAULT_WORKBOOK)
    p.add_argument("--fdga-dir", type=Path, default=_FDGA_DIR)
    p.add_argument("--csv", type=Path, default=None,
                   help="where to write the full comparison "
                        "(default: <fdga-dir>/reconciliation.csv)")
    p.add_argument("--no-write", action="store_true",
                   help="print the comparison without writing it")
    args = p.parse_args()
    if args.csv is None:
        args.csv = args.fdga_dir / "reconciliation.csv"

    if not args.workbook.exists():
        raise SystemExit(f"Workbook not found: {args.workbook}")
    cy_path = args.fdga_dir / "chamber_year.csv"
    if not cy_path.exists():
        raise SystemExit(f"{cy_path} not found — run build_fdga_cdm.py first.")

    cdm = pd.read_csv(cy_path)
    book = read_workbook(args.workbook)
    result = reconcile(cdm, book)

    counts = result["status"].value_counts().to_dict()
    total = len(result)
    matched = counts.get("MATCH", 0)
    print(f"Reconciliation: {matched}/{total} cells match "
          f"({matched / total:.1%})")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    diffs = result[result["status"] == "DIFF"]
    if len(diffs):
        print(f"\n{len(diffs)} difference(s)")
        print("-" * 74)
        print(f"{'cycle':>5} {'chamber':>13} {'field':>18} {'CDM':>7} "
              f"{'workbook':>9} {'delta':>7}")
        for r in diffs.itertuples():
            # Columns arrive as float when any row in them is null.
            print(f"{int(r.cycle_year):5d} {r.chamber:>13} {r.field:>18} "
                  f"{int(r.cdm):7d} {int(r.workbook):9d} {int(r.delta):+7d}")

    nulls = result[result["status"] == "CDM_NULL"]
    if len(nulls):
        print(f"\n{len(nulls)} cell(s) the CDM cannot derive "
              f"(see _validation for the documented reason)")
        for r in nulls.itertuples():
            print(f"  {r.cycle_year} {r.chamber:>13} {r.field:>18} "
                  f"workbook={r.workbook}")

    if not args.no_write:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(args.csv, index=False)
        print(f"\nFull comparison -> {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
