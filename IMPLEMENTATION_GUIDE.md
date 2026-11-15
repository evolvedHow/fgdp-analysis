# Implementation Guide: Election Certification Status Tracking

## Overview

This guide walks through implementing certification status tracking for the Georgia 2026 election results in the FDP data platform.

---

## Files Created

### Analysis & Documentation
- **`ELECTION_ANALYSIS_2026.md`** — Comprehensive preliminary analysis of voting data
- **`IMPLEMENTATION_GUIDE.md`** — This file

### Scripts
- **`scripts/add_certification_tracking.py`** — Extend election data with certification columns

### Schema & Models
- **`fdp/config/schema/elections.yml`** — Schema definition for election data
- **`fdp/fdp/loaders/elections_enhanced.py`** — Enhanced loader with certification support

---

## Step-by-Step Implementation

### Phase 1: Extend Current Data (TODAY)

#### Step 1: Add Certification Columns to Excel File

```bash
cd ~/codebox/fgdp

# Run the certification tracking script
python scripts/add_certification_tracking.py \
  --input requirements/ElectionVotResults-2026-Uncertified.xlsx \
  --output requirements/ElectionVotResults-2026-v2.xlsx \
  --status uncertified \
  --audit-status pending
```

**What this does:**
- Reads the existing election results
- Adds 5 new columns to each sheet:
  - `certification_status` = "uncertified"
  - `certified_date` = None (not yet certified)
  - `certified_by` = None (not yet certified)
  - `audit_status` = "pending"
  - `caveat_notes` = None
- Applies formatting (yellow highlighting) to new columns
- Saves enhanced file as v2

**Output:**
```
📖 Reading: requirements/ElectionVotResults-2026-Uncertified.xlsx
  ▶️  Processing sheet: Total Votes
     ✅ Added 5 certification columns (730 rows)
  ▶️  Processing sheet: Total Votes by Group
     ✅ Added 5 certification columns (2,920 rows)
  ▶️  Processing sheet: County Results
     ✅ Added 5 certification columns (11,863 rows)

💾 Writing: requirements/ElectionVotResults-2026-v2.xlsx
✅ Complete! Output saved to requirements/ElectionVotResults-2026-v2.xlsx
```

---

### Phase 2: Update FDP Integration (THIS WEEK)

#### Step 2: Convert to FDP Parquet Format

Create a migration script that:

```python
# scripts/migrate_to_fdp.py
import pandas as pd
from pathlib import Path

input_file = Path("requirements/ElectionVotResults-2026-v2.xlsx")
output_dir = Path("fdp/data/repos/main/elections")

# Read all sheets
sheets = pd.read_excel(input_file, sheet_name=None)

# Combine all sheets into canonical format
dfs = []
for sheet_name, df in sheets.items():
    df['source_sheet'] = sheet_name
    dfs.append(df)

canonical_df = pd.concat(dfs, ignore_index=True)

# Save as parquet
canonical_df.to_parquet(
    output_dir / "dim_elections_2026_uncertified.parquet",
    index=False
)

print(f"✅ Migrated {len(canonical_df)} election records to FDP")
```

#### Step 3: Update FDP Loaders

The enhanced loader (`elections_enhanced.py`) provides:

```python
from fdp.loaders.elections_enhanced import ElectionLoaderEnhanced

# Initialize loader
loader = ElectionLoaderEnhanced(repo)

# Load all elections (including uncertified)
all_elections = loader.load("elections_2026")

# Load only certified results
certified_only = loader.load("elections_2026", certification_status="certified")

# Show certification summary
summary = loader.get_certification_summary(all_elections)
print(summary)
# Output:
# {
#   'total_records': 11863,
#   'by_status': {
#     'uncertified': 11863,
#     'certified': 0,
#     'certified_with_caveats': 0
#   },
#   'by_audit': {
#     'pending': 11863
#   },
#   'with_caveats': 0
# }
```

---

### Phase 3: Update Data As Results Certify (ONGOING)

#### Step 4: Implement Certification Update Workflow

When Georgia SOS certifies results:

```python
# scripts/update_certification_status.py
import pandas as pd
from datetime import datetime

def certify_results(
    parquet_file: str,
    county_name: str = None,  # Certify specific county or all
    office_names: list[str] = None,  # Certify specific offices or all
):
    """
    Update records to certified status.
    
    Args:
        parquet_file: Path to election parquet
        county_name: Filter by county (None = all)
        office_names: Filter by office names (None = all)
    """
    df = pd.read_parquet(parquet_file)
    
    # Build filter
    mask = pd.Series([True] * len(df))
    
    if county_name:
        mask &= df['county'] == county_name
    
    if office_names:
        mask &= df['office_name'].isin(office_names)
    
    # Update certification fields
    df.loc[mask, 'certification_status'] = 'certified'
    df.loc[mask, 'certified_date'] = datetime.now().strftime('%Y-%m-%d')
    df.loc[mask, 'certified_by'] = 'Georgia Secretary of State'
    df.loc[mask, 'audit_status'] = 'complete'
    df.loc[mask, 'caveat_notes'] = None
    
    # Save updated
    df.to_parquet(parquet_file)
    
    # Log
    print(f"✅ Certified {mask.sum()} records")
```

---

## Usage Examples

### Example 1: Filter Uncertified Results

```python
from fdp import DataPlatform
from fdp.loaders.elections_enhanced import ElectionLoaderEnhanced

platform = DataPlatform()
loader = ElectionLoaderEnhanced(platform.main_repo)

# Get all uncertified results
uncertified = loader.load("elections_2026", certification_status="uncertified")
print(f"Uncertified records: {len(uncertified)}")

# By county
fulton_uncertified = uncertified[uncertified['county'] == 'Fulton County']
print(f"Fulton County uncertified: {len(fulton_uncertified)}")
```

### Example 2: Monitor Certification Progress

```python
def report_certification_status(df):
    """Generate certification status report."""
    summary = {
        'Total': len(df),
        'Uncertified': len(df[df['certification_status'] == 'uncertified']),
        'Certified': len(df[df['certification_status'] == 'certified']),
        'With Caveats': len(df[df['certification_status'] == 'certified_with_caveats']),
        'Pending Audit': len(df[df['audit_status'] == 'in_progress']),
    }
    
    print("\n📊 CERTIFICATION STATUS REPORT")
    print("=" * 50)
    for key, count in summary.items():
        pct = (count / summary['Total'] * 100) if summary['Total'] > 0 else 0
        print(f"{key:.<30} {count:>8,} ({pct:>6.1f}%)")
    
    return summary

# Usage
report_certification_status(df)
```

Output:
```
📊 CERTIFICATION STATUS REPORT
==================================================
Total............................... 11,863 (100.0%)
Uncertified......................... 11,863 (100.0%)
Certified.............................     0 (  0.0%)
With Caveats..........................     0 (  0.0%)
Pending Audit.........................  11,863 (100.0%)
```

### Example 3: Compare Certified vs Uncertified

```python
def compare_results(df):
    """Compare certified vs uncertified results."""
    certified = df[df['certification_status'] == 'certified']
    uncertified = df[df['certification_status'] == 'uncertified']
    
    print("\nCERTIFIED VS UNCERTIFIED COMPARISON")
    print(f"Certified contests: {certified['contest_id'].nunique()}")
    print(f"Uncertified contests: {uncertified['contest_id'].nunique()}")
    print(f"Certified counties: {certified['county'].nunique()}")
    print(f"Uncertified counties: {uncertified['county'].nunique()}")
    
    # Find gaps
    cert_contests = set(certified['contest_id'].unique())
    uncert_contests = set(uncertified['contest_id'].unique())
    
    missing_cert = uncert_contests - cert_contests
    if missing_cert:
        print(f"\nStill pending certification: {missing_cert}")

compare_results(df)
```

---

## Database Schema (PostgreSQL)

For optional PostgreSQL integration:

```sql
CREATE TABLE elections (
    id SERIAL PRIMARY KEY,
    county VARCHAR(100) NOT NULL,
    office_name VARCHAR(200) NOT NULL,
    contest_id VARCHAR(50) NOT NULL,
    ballot_name VARCHAR(200) NOT NULL,
    choice_id FLOAT,
    party VARCHAR(20),
    total INTEGER NOT NULL,
    
    -- Certification tracking
    certification_status VARCHAR(50) NOT NULL 
        CHECK (certification_status IN ('uncertified', 'certified', 'certified_with_caveats')),
    certified_date DATE,
    certified_by VARCHAR(200),
    audit_status VARCHAR(50)
        CHECK (audit_status IS NULL OR audit_status IN ('pending', 'in_progress', 'complete', 'flagged')),
    caveat_notes TEXT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    UNIQUE(county, contest_id, choice_id),
    INDEX idx_cert_status (certification_status),
    INDEX idx_audit_status (audit_status),
    INDEX idx_county (county),
    INDEX idx_office (office_name)
);
```

---

## Testing & Validation

### Test the Script

```bash
# Test with sample data
cd ~/codebox/fgdp

# Create test file with just headers
python -c "
import pandas as pd
df = pd.DataFrame({
    'County': ['Test County'],
    'Office Name': ['US Senate'],
    'Contest ID': ['US2'],
    'Ballot Name': ['Test Candidate'],
    'Choice ID': [1.0],
    'Party': ['Rep'],
    'Total': [1000]
})
df.to_excel('test_election_data.xlsx', index=False)
"

# Run script on test file
python scripts/add_certification_tracking.py \
  --input test_election_data.xlsx \
  --output test_election_data_output.xlsx \
  --status uncertified

# Verify
python -c "
import pandas as pd
df = pd.read_excel('test_election_data_output.xlsx')
print(df.columns.tolist())
print(df.head())
"
```

Expected output:
```
['County', 'Office Name', 'Contest ID', 'Ballot Name', 'Choice ID', 'Party', 'Total', 
 'certification_status', 'certified_date', 'certified_by', 'audit_status', 'caveat_notes']
```

---

## Troubleshooting

### Issue: Script fails with "openpyxl not found"
```bash
cd ~/codebox/fgdp/fdp
uv sync  # Reinstall dependencies
```

### Issue: Excel file has formatting errors
- The script uses `openpyxl` which may have issues with some Excel features
- Ensure the input file is saved as `.xlsx` (not `.xls`)
- Try opening the file in Excel and re-saving to ensure compatibility

### Issue: Certification status not filtering correctly
```python
# Debug: Check actual values in dataframe
print(df['certification_status'].unique())
print(df['certification_status'].value_counts())

# Ensure no whitespace
df['certification_status'] = df['certification_status'].str.strip()
```

---

## Next Steps

### Week 1
- [ ] Run `add_certification_tracking.py` on current election file
- [ ] Verify output Excel file has all columns
- [ ] Test loading with enhanced loader

### Week 2
- [ ] Migrate to FDP parquet format
- [ ] Integrate enhanced loader into FDP
- [ ] Create certification status dashboard

### Week 3+
- [ ] Implement automated certification updates from GA SOS
- [ ] Create reconciliation reports
- [ ] Set up certification audit trail
- [ ] Build historical versioning system

---

## Questions?

Refer to:
- **Analysis:** `ELECTION_ANALYSIS_2026.md`
- **Schema:** `fdp/config/schema/elections.yml`
- **Enhanced Loader:** `fdp/fdp/loaders/elections_enhanced.py`
- **Script Help:** `python scripts/add_certification_tracking.py --help`
