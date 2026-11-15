#!/usr/bin/env python3
"""Ingest 2026 Georgia election results into FDP canonical model.

Reads the 2026 uncertified election results from Excel and adds them to
the FDP fdga parquet files (statewide, chamber_year, contests, facts).

Usage
-----
    cd ~/codebox/fgdp/fdp && .venv/bin/python ../scripts/ingest_2026_elections.py
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT / "requirements" / "ElectionVotResults-2026-Certified-v2.xlsx"
REPO = ROOT / "fdp" / "data" / "repos" / "main"
FDGA_DIR = REPO / "fdga"

# 2026 election metadata
ELECTION_DATE = "2026-11-03"  # Election day
CYCLE_YEAR = 2026
ELECTION_TYPE = "general"

def load_2026_data() -> dict:
    """Load 2026 election results from Excel file."""
    print(f"📖 Reading {INPUT_FILE}...")
    
    sheets = {}
    for sheet in ["Total Votes", "Total Votes by Group", "County Results"]:
        df = pd.read_excel(INPUT_FILE, sheet_name=sheet)
        sheets[sheet] = df
        print(f"   ✓ {sheet}: {len(df)} rows")
    
    return sheets

def ingest_2026() -> None:
    """Ingest 2026 data into FDP canonical model."""
    
    # Load existing parquets
    print("\n📂 Loading existing FDP data...")
    statewide = pd.read_parquet(FDGA_DIR / "statewide.parquet")
    contests = pd.read_parquet(FDGA_DIR / "contests.parquet")
    facts = pd.read_parquet(FDGA_DIR / "facts.parquet")
    chamber_year = pd.read_parquet(FDGA_DIR / "chamber_year.parquet")
    
    print(f"   ✓ statewide: {len(statewide)} rows")
    print(f"   ✓ contests: {len(contests)} rows")
    print(f"   ✓ facts: {len(facts)} rows")
    print(f"   ✓ chamber_year: {len(chamber_year)} rows")
    
    # Load 2026 data
    sheets = load_2026_data()
    total_votes = sheets["Total Votes"]
    
    print("\n⚠️  2026 DATA INGESTION")
    print("─" * 60)
    print("\nThis script is a template for ingesting 2026 election data.")
    print("To complete the integration, you need to:")
    print("")
    print("1. Structure the 2026 data to match FDP canonical model:")
    print("   - statewide.parquet (state-level results)")
    print("   - chamber_year.parquet (seats-vs-votes by chamber)")
    print("   - contests.parquet (per-district results)")
    print("   - facts.parquet (individual candidate results)")
    print("")
    print("2. Consider certification status:")
    print("   - Current: 100% uncertified, audit_status=pending")
    print("   - Add certification_status column to track")
    print("")
    print("3. Map 2026 data fields to FDP canonical model:")
    
    print(f"\nAvailable in 2026 data:")
    print(f"  Columns: {list(total_votes.columns)}")
    print(f"  Sample offices: {total_votes['Office Name'].unique()[:3].tolist()}")
    print(f"  Total records: {len(total_votes)}")
    
    print("\n✅ NEXT STEPS:")
    print("─" * 60)
    print("")
    print("Option A: Use FDP ingest/elections.py (if available)")
    print("  See: fdp/fdp/ingest/elections.py")
    print("")
    print("Option B: Run build_fdga_cdm.py to regenerate from raw data")
    print("  cd ~/codebox/fgdp/fdp")
    print("  .venv/bin/python scripts/build_fdga_cdm.py")
    print("")
    print("Once 2026 is in the fdga parquets, run:")
    print("  cd ~/codebox/fgdp/fdp")
    print("  .venv/bin/python ../scripts/export_story_data.py")
    print("")
    print("This will add 2026 to fair-districts-xray/public/data/story.json")
    print("")

if __name__ == "__main__":
    ingest_2026()
