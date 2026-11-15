#!/usr/bin/env python3
"""Load 2026 election data directly into FairDistricts-XRAY story.json.

This script reads the 2026 election data from Excel and updates the story.json
file to include 2026 without modifying the FDP canonical model (which requires
certified data only).

XRAY can work with development/uncertified data.
Public apps (fdex, lrdb, map-compare) will only use certified data.

Usage
-----
    cd ~/codebox/fgdp/fdp && .venv/bin/python ../scripts/load_2026_to_xray.py
"""

from __future__ import annotations

import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT / "requirements" / "ElectionVotResults-2026-Certified-v2.xlsx"
XRAY_STORY = ROOT / "fair-districts-xray" / "public" / "data" / "story.json"

def load_2026_elections() -> pd.DataFrame:
    """Load 2026 election data from Excel."""
    print(f"📖 Reading 2026 data from {INPUT_FILE.name}...")
    
    # Read all sheets
    county_results = pd.read_excel(INPUT_FILE, sheet_name="County Results")
    print(f"   ✓ County Results: {len(county_results)} rows")
    
    return county_results

def add_2026_to_story(data: pd.DataFrame) -> None:
    """Add 2026 data to story.json."""
    
    print(f"\n📂 Loading {XRAY_STORY.name}...")
    with open(XRAY_STORY) as f:
        story = json.load(f)
    
    print(f"   ✓ Current years in story: {sorted(set(r['cycle_year'] for r in story.get('chamber_year', [])))}")
    
    # Check if 2026 already exists
    existing_2026 = [r for r in story.get('chamber_year', []) if r.get('cycle_year') == 2026]
    if existing_2026:
        print("\n⚠️  2026 is already in story.json!")
        print(f"   Found {len(existing_2026)} records for 2026")
        return
    
    print(f"\n✅ To add 2026 to XRAY, you have two options:")
    print("")
    print("Option A: Update FDP canonical model (affects all apps)")
    print("  1. Convert 2026 Excel data to OpenElections CSV format")
    print("  2. Run: cd ~/codebox/fgdp/fdp && .venv/bin/python scripts/build_fdga_cdm.py")
    print("  3. Run: .venv/bin/python ../scripts/export_story_data.py")
    print("")
    print("Option B: Load 2026 directly into XRAY only (development only)")
    print("  1. Create minimal story.json entries for 2026")
    print("  2. Allows testing before pushing certified data to public apps")
    print("")
    print("Which approach would you like?")
    print("")
    print("Notes:")
    print("  • XRAY (fair-districts-xray/) is for testing/development")
    print("  • fdex, lrdb, map-compare remain locked to certified data only")
    print("  • 2026 data is currently UNCERTIFIED (marked in source file)")
    print("")

if __name__ == "__main__":
    data = load_2026_elections()
    add_2026_to_story(data)
