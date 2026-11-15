#!/usr/bin/env python3
"""
Add certification status tracking to election results.

This script extends the existing election data with certification status fields:
- certification_status: uncertified | certified | certified_with_caveats
- certified_date: Date of official certification (ISO format)
- certified_by: Official/entity that certified results
- audit_status: pending | in_progress | complete | flagged
- caveat_notes: Any notes about the certification

Usage:
    python scripts/add_certification_tracking.py \
        --input requirements/ElectionVotResults-2026-Uncertified.xlsx \
        --output requirements/ElectionVotResults-2026-Uncertified-v2.xlsx \
        --status uncertified
"""

import argparse
from pathlib import Path
from datetime import datetime
from typing import Literal

import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Alignment

# Define certification status types
CertificationStatus = Literal["uncertified", "certified", "certified_with_caveats"]
AuditStatus = Literal["pending", "in_progress", "complete", "flagged"]


def add_certification_columns(
    df: pd.DataFrame,
    certification_status: CertificationStatus = "uncertified",
    certified_date: str | None = None,
    certified_by: str | None = None,
    audit_status: AuditStatus = "pending",
    caveat_notes: str | None = None,
) -> pd.DataFrame:
    """
    Add certification tracking columns to election results dataframe.

    Args:
        df: Input dataframe with election results
        certification_status: Current certification status (default: uncertified)
        certified_date: Date of certification in ISO format (YYYY-MM-DD)
        certified_by: Who certified the results (e.g., "Georgia Secretary of State")
        audit_status: Current audit status (default: pending)
        caveat_notes: Any additional notes about certification

    Returns:
        DataFrame with new certification columns
    """
    df = df.copy()

    # Add certification columns
    df.insert(len(df.columns), "certification_status", certification_status)
    df.insert(len(df.columns), "certified_date", certified_date)
    df.insert(len(df.columns), "certified_by", certified_by)
    df.insert(len(df.columns), "audit_status", audit_status)
    df.insert(len(df.columns), "caveat_notes", caveat_notes)

    return df


def process_excel_file(
    input_path: str | Path,
    output_path: str | Path,
    certification_status: CertificationStatus = "uncertified",
    certified_date: str | None = None,
    certified_by: str | None = None,
    audit_status: AuditStatus = "pending",
) -> None:
    """
    Process Excel file and add certification columns to all sheets.

    Args:
        input_path: Path to input Excel file
        output_path: Path to output Excel file
        certification_status: Certification status for all records
        certified_date: Date of certification
        certified_by: Who certified
        audit_status: Audit status for all records
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    print(f"📖 Reading: {input_path}")
    excel_file = pd.ExcelFile(input_path)
    sheet_names = excel_file.sheet_names

    # Process each sheet
    sheets = {}
    for sheet in sheet_names:
        print(f"  ▶️  Processing sheet: {sheet}")
        df = pd.read_excel(input_path, sheet_name=sheet)
        df_with_cert = add_certification_columns(
            df,
            certification_status=certification_status,
            certified_date=certified_date,
            certified_by=certified_by,
            audit_status=audit_status,
        )
        sheets[sheet] = df_with_cert
        print(f"     ✅ Added 5 certification columns ({len(df_with_cert)} rows)")

    # Write to Excel
    print(f"\n💾 Writing: {output_path}")
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    # Apply formatting to Excel file
    _format_excel_output(output_path)

    print(f"✅ Complete! Output saved to {output_path}")
    print_summary(sheets)


def _format_excel_output(output_path: Path) -> None:
    """Apply formatting to the output Excel file."""
    wb = openpyxl.load_workbook(output_path)

    # Define fill colors for new columns
    cert_status_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    for sheet in wb.sheetnames:
        ws = wb[sheet]

        # Find certification columns (they should be last 5)
        cert_columns = ["certification_status", "certified_date", "certified_by", "audit_status", "caveat_notes"]
        col_map = {}

        for col_idx, cell in enumerate(ws[1], start=1):
            if cell.value in cert_columns:
                col_map[cell.value] = col_idx

        # Apply formatting
        for col_name, col_idx in col_map.items():
            col_letter = get_column_letter(col_idx)
            # Header
            ws[f"{col_letter}1"].fill = header_fill
            ws[f"{col_letter}1"].alignment = Alignment(horizontal="center", wrap_text=True)

            # Data rows
            for row_idx in range(2, ws.max_row + 1):
                ws[f"{col_letter}{row_idx}"].fill = cert_status_fill
                ws[f"{col_letter}{row_idx}"].alignment = Alignment(horizontal="left", wrap_text=True)

    wb.save(output_path)


def print_summary(sheets: dict[str, pd.DataFrame]) -> None:
    """Print summary of processed data."""
    print("\n" + "=" * 80)
    print("CERTIFICATION TRACKING - DATA SUMMARY")
    print("=" * 80)

    for sheet_name, df in sheets.items():
        print(f"\n📊 Sheet: {sheet_name}")
        print(f"   Rows: {len(df):,}")
        print(f"   Columns: {len(df.columns)}")
        print(f"   Certification Status: {df['certification_status'].unique()[0]}")
        print(f"   Audit Status: {df['audit_status'].unique()[0] if 'audit_status' in df.columns else 'N/A'}")

        # Show unique values in certification fields
        if "certification_status" in df.columns:
            statuses = df["certification_status"].unique()
            print(f"   → Statuses: {', '.join(statuses)}")


def main():
    parser = argparse.ArgumentParser(
        description="Add certification status tracking to election results"
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to input Excel file",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to output Excel file",
    )
    parser.add_argument(
        "--status",
        type=str,
        choices=["uncertified", "certified", "certified_with_caveats"],
        default="uncertified",
        help="Certification status for all records",
    )
    parser.add_argument(
        "--certified-date",
        type=str,
        default=None,
        help="Certification date (ISO format: YYYY-MM-DD)",
    )
    parser.add_argument(
        "--certified-by",
        type=str,
        default=None,
        help="Who certified the results",
    )
    parser.add_argument(
        "--audit-status",
        type=str,
        choices=["pending", "in_progress", "complete", "flagged"],
        default="pending",
        help="Audit status",
    )

    args = parser.parse_args()

    process_excel_file(
        input_path=args.input,
        output_path=args.output,
        certification_status=args.status,
        certified_date=args.certified_date,
        certified_by=args.certified_by,
        audit_status=args.audit_status,
    )


if __name__ == "__main__":
    main()
