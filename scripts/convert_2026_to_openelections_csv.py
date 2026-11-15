#!/usr/bin/env python3
"""Convert 2026 election Excel to OpenElections CSV format for FDP canonical model.

The OpenElections format for Georgia county-level results:
  county,office,district,candidate,party,votes

This script reads from ElectionVotResults-2026-Certified-v2.xlsx and creates
2026/20261103__ga__general__county-level.csv in OpenElections format.

Usage
-----
    cd ~/codebox/fgdp/fdp && .venv/bin/python ../scripts/convert_2026_to_openelections_csv.py
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT / "requirements" / "ElectionVotResults-2026-Certified-v2.xlsx"
OUTPUT_DIR = ROOT / "fdp" / "data" / "repos" / "main" / "openelections" / "2026"
OUTPUT_FILE = OUTPUT_DIR / "20261103__ga__general__county-level.csv"

# Mapping of office names to OpenElections format
OFFICE_MAP = {
    "President": "President",
    "U.S. Senator": "U.S. Senate",
    "U.S. Representative": "U.S. House",
    "State Senator": "State Senate",
    "State Representative": "State House",
    "Governor": "Governor",
    "Secretary of State": "Secretary of State",
    "Attorney General": "Attorney General",
    "State Auditor": "Auditor",
    "Comptroller": "Comptroller General",
    "Commissioner of Labor": "Commissioner of Labor",
    "Commissioner of Insurance": "Insurance Commissioner",
    "Public Service Commissioner": "Public Service Commission",
    "State School Board": "State School Board",
}

# Party name normalization
PARTY_MAP = {
    "D": "Democratic",
    "R": "Republican",
    "L": "Libertarian",
    "G": "Green",
    "I": "Independent",
    "W": "Write-in",
}

def normalize_office(office: str) -> Optional[str]:
    """Normalize office name to OpenElections standard."""
    for key, val in OFFICE_MAP.items():
        if key.lower() in office.lower():
            return val
    return office

def normalize_party(party: str) -> str:
    """Normalize party code."""
    party_clean = party.strip().upper()
    return PARTY_MAP.get(party_clean, party_clean)

def convert_2026() -> None:
    """Convert 2026 Excel to OpenElections CSV."""
    
    print(f"📖 Reading {INPUT_FILE.name}...")
    if not INPUT_FILE.exists():
        print(f"❌ File not found: {INPUT_FILE}")
        return
    
    # Read the County Results sheet
    df = pd.read_excel(INPUT_FILE, sheet_name="County Results")
    print(f"✓ Loaded {len(df)} rows from 'County Results'")
    
    # Expected columns: County Name, Office Name, District, Candidate Name, Party, Votes
    required_cols = ["County Name", "Office Name", "District", "Candidate Name", "Party", "Votes"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"❌ Missing columns: {missing}")
        print(f"   Available: {list(df.columns)}")
        return
    
    # Convert to OpenElections format
    result = []
    for _, row in df.iterrows():
        office = normalize_office(row["Office Name"])
        party = normalize_party(row["Party"])
        
        record = {
            "county": row["County Name"].strip(),
            "office": office,
            "district": row["District"] if pd.notna(row["District"]) else "",
            "candidate": row["Candidate Name"].strip(),
            "party": party,
            "votes": int(row["Votes"]) if pd.notna(row["Votes"]) else 0,
        }
        result.append(record)
    
    result_df = pd.DataFrame(result)
    print(f"✓ Converted to {len(result_df)} OpenElections records")
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write CSV
    result_df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Wrote to {OUTPUT_FILE}")
    print(f"   Shape: {result_df.shape}")
    print(f"   Sample:\n{result_df.head(3).to_string()}")
    
    # Print summary
    print(f"\n📊 Summary:")
    print(f"   Counties: {result_df['county'].nunique()}")
    print(f"   Offices: {result_df['office'].nunique()} → {sorted(result_df['office'].unique())}")
    print(f"   Parties: {result_df['party'].nunique()} → {sorted(result_df['party'].unique())}")
    print(f"   Total Votes: {result_df['votes'].sum():,}")
    
    print(f"\n✅ Ready for FDP build:")
    print(f"   cd ~/codebox/fgdp/fdp")
    print(f"   .venv/bin/python scripts/build_fdga_cdm.py")

if __name__ == "__main__":
    convert_2026()
