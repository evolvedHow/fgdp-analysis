# Quick Start: Certification Tracking

Get the certification tracking system running in 5 minutes.

---

## 1️⃣ Add Certification Fields to Your Data (2 min)

```bash
cd ~/codebox/fgdp/fdp

# Run the script to add 5 certification columns
uv run python ../scripts/add_certification_tracking.py \
  --input ../requirements/ElectionVotResults-2026-Uncertified.xlsx \
  --output ../requirements/ElectionVotResults-2026-v2.xlsx \
  --status uncertified \
  --audit-status pending
```

✅ Output: `ElectionVotResults-2026-v2.xlsx` with certification columns added

---

## 2️⃣ Load Data with Enhanced Loader (1 min)

```python
from fdp.loaders.elections_enhanced import ElectionLoaderEnhanced
from fdp import DataPlatform

# Initialize
platform = DataPlatform()
loader = ElectionLoaderEnhanced(platform.main_repo)

# Load all elections
all_elections = loader.load("elections")

# Load only certified
certified = loader.load("elections", certification_status="certified")

# Get summary
summary = loader.get_certification_summary(all_elections)
print(summary)
```

---

## 3️⃣ Update Status When Certified (1 min)

When Georgia SOS certifies results:

```python
import pandas as pd

# Read the file
df = pd.read_excel("ElectionVotResults-2026-v2.xlsx", sheet_name="County Results")

# Update Fulton County to certified
mask = df['County'] == 'Fulton County'
df.loc[mask, 'certification_status'] = 'certified'
df.loc[mask, 'certified_date'] = '2026-11-14'
df.loc[mask, 'certified_by'] = 'Fulton County Elections Director'
df.loc[mask, 'audit_status'] = 'complete'

# Save
df.to_excel("ElectionVotResults-2026-v2.xlsx", sheet_name="County Results", index=False)

print(f"✅ Updated {mask.sum()} Fulton County records to certified")
```

---

## 4️⃣ Push to FDP (1 min)

```bash
# Convert to parquet
cd ~/codebox/fgdp/fdp
uv run python << 'EOF'
import pandas as pd

# Read all sheets
dfs = pd.read_excel("../requirements/ElectionVotResults-2026-v2.xlsx", sheet_name=None)

# Combine into single canonical dataset
all_data = pd.concat(dfs.values(), ignore_index=True)

# Save to FDP elections directory
all_data.to_parquet("data/repos/main/elections/dim_elections_2026.parquet")

print(f"✅ Saved {len(all_data)} records to FDP")
EOF
```

---

## Common Queries

### Show All Uncertified Records

```python
import pandas as pd

df = pd.read_excel("ElectionVotResults-2026-v2.xlsx", sheet_name="County Results")
uncertified = df[df['certification_status'] == 'uncertified']

print(f"Total uncertified: {len(uncertified):,}")
print(f"Counties affected: {uncertified['County'].nunique()}")
print(f"Contests affected: {uncertified['Office Name'].nunique()}")
```

### Show Certification Status by County

```python
df = pd.read_excel("ElectionVotResults-2026-v2.xlsx", sheet_name="County Results")

status_by_county = df.groupby('County')['certification_status'].value_counts().unstack(fill_value=0)
print(status_by_county)
```

### Find Records with Caveats

```python
df = pd.read_excel("ElectionVotResults-2026-v2.xlsx", sheet_name="County Results")

with_caveats = df[df['caveat_notes'].notna()]
print(f"Records with caveats: {len(with_caveats)}")
print(with_caveats[['County', 'Office Name', 'caveat_notes']].drop_duplicates())
```

---

## Column Reference

| Column | Type | Values | When to Use |
|--------|------|--------|------------|
| `certification_status` | string | uncertified, certified, certified_with_caveats | Always required |
| `certified_date` | date | YYYY-MM-DD or NULL | When results are certified |
| `certified_by` | string | Official name or NULL | Who certified (e.g., "GA Secretary of State") |
| `audit_status` | string | pending, in_progress, complete, flagged | Track audit lifecycle |
| `caveat_notes` | string | Free text or NULL | Issues/notes about certification |

---

## Status Combinations

### Workflow 1: Not Yet Certified
```
certification_status: uncertified
certified_date: NULL
certified_by: NULL
audit_status: pending
caveat_notes: NULL
```

### Workflow 2: Just Certified
```
certification_status: certified
certified_date: 2026-11-14
certified_by: Georgia Secretary of State
audit_status: complete
caveat_notes: NULL
```

### Workflow 3: Certified with Issues
```
certification_status: certified_with_caveats
certified_date: 2026-11-14
certified_by: County Elections
audit_status: complete
caveat_notes: Awaiting resolution of 5 provisional ballots
```

### Workflow 4: Recounting
```
certification_status: uncertified
certified_date: 2026-11-10  # Previous cert date
certified_by: GA Secretary of State  # Who originally certified
audit_status: in_progress  # Now auditing
caveat_notes: Recount in progress for District 5
```

---

## Help

**Script help:**
```bash
python scripts/add_certification_tracking.py --help
```

**Python API help:**
```python
from fdp.loaders.elections_enhanced import ElectionLoaderEnhanced
help(ElectionLoaderEnhanced)
```

**More info:**
- `ELECTION_ANALYSIS_2026.md` — Full data analysis
- `IMPLEMENTATION_GUIDE.md` — Detailed steps
- `CERTIFICATION_TRACKING_SUMMARY.md` — Complete overview
- `fdp/config/schema/elections.yml` — Schema specification

---

**Questions?** Check the detailed guides or contact the FDP team.
