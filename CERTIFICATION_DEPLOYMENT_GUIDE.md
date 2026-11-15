# 2026 Certification Deployment Guide

**Status:** 2026 data loaded to XRAY (UNCERTIFIED)  
**Last Updated:** November 15, 2026  
**Next Action:** When GA SOS certifies, follow procedures below

---

## Overview

The 2026 Georgia election data is currently in the system but marked as **UNCERTIFIED**:

- ✅ **XRAY** (fair-districts-xray): Shows 2026 data for development/testing
- ❌ **Public Apps** (fdex, lrdb, map-compare, fdensemble): Filter out 2026 (only show certified data)

When Georgia Secretary of State certifies the results (~November 14, 2026), follow the procedures in this guide to make 2026 available to all apps.

---

## Part 1: When GA SOS Certifies — Update the Canonical Model

### Step 1: Update the Certification Flag

Edit `~/codebox/fgdp/fdp/fdp/cdm/sources.py`:

```python
    2026: Source(
        source_id="oe_ga_20261103_general",
        election_date="2026-11-03", cycle_year=2026, election_type="general",
        patterns=("2026/20261103__ga__general__county-level.csv",),
        votes_total_column="votes", grain="county",
        certified=True,  # ← CHANGE FROM False TO True
        note="Georgia Secretary of State certified results on [DATE].",
    ),
```

### Step 2: Rebuild the Canonical Model

```bash
cd ~/codebox/fgdp/fdp
.venv/bin/python scripts/build_fdga_cdm.py
```

This regenerates the parquet files with the updated certification status.

### Step 3: Export Updated Data to story.json

```bash
cd ~/codebox/fgdp/fdp
.venv/bin/python ../scripts/export_story_data.py
```

This creates a new story.json with 2026 data marked as certified.

### Step 4: Copy to XRAY

```bash
cp ~/codebox/fgdp/public/data/story.json \
   ~/codebox/fgdp/fair-districts-xray/public/data/story.json
```

### Step 5: Commit and Push All Changes

```bash
# Commit in fgdp
cd ~/codebox/fgdp
git add -A
git commit -m "feat: Mark 2026 as certified by GA SOS

- Update cdm/sources.py: certified=True for 2026
- Rebuild canonical model with build_fdga_cdm.py
- Re-export story.json with certified data
- 2026 now available to all public-facing apps (fdex, lrdb, map-compare)"
git push origin main

# Commit in fair-districts-xray
cd ~/codebox/fgdp/fair-districts-xray
git add public/data/story.json
git commit -m "data: Update story.json with certified 2026 election results"
git push origin main
```

---

## Part 2: Verification Steps

After pushing, verify that public apps will now show 2026:

### Check 1: Verify 2026 is in story.json

```bash
cd ~/codebox/fgdp && python3 << 'EOF'
import json
with open('public/data/story.json') as f:
    data = json.load(f)
years = sorted(set(e['year'] for e in data['statewide']))
print(f"Years in story.json: {years}")
if 2026 in years:
    print("✅ 2026 is present and certified")
else:
    print("❌ 2026 NOT found - check build_fdga_cdm.py output")
EOF
```

### Check 2: Verify fdp parquets have 2026

```bash
cd ~/codebox/fgdp/fdp && .venv/bin/python << 'EOF'
import pandas as pd
stw = pd.read_parquet('data/repos/main/fdga/statewide.parquet')
cy = pd.read_parquet('data/repos/main/fdga/chamber_year.parquet')
print(f"Statewide cycles: {sorted(stw['cycle_year'].unique())}")
print(f"Chamber_year cycles: {sorted(cy['cycle_year'].unique())}")
EOF
```

### Check 3: Rebuild fdex/lrdb/map-compare to pick up new story.json

Each public app reads story.json at build time. Trigger a rebuild:

```bash
# For fdex
cd ~/codebox/fgdp/fdex && npm run build

# For lrdb
cd ~/codebox/fgdp/lrdb && npm run build

# For map-compare
cd ~/codebox/fgdp/map-compare && npm run build

# For fdensemble
cd ~/codebox/fgdp/fdensemble && npm run build
```

---

## Part 3: Reference Information

### File Locations

| Component | Location | Purpose |
|-----------|----------|---------|
| **Certification Flag** | `fdp/fdp/cdm/sources.py` | Source registry; controls certified/uncertified |
| **Build Script** | `fdp/scripts/build_fdga_cdm.py` | Regenerates parquets from OpenElections CSVs |
| **Export Script** | `scripts/export_story_data.py` | Creates story.json from parquets |
| **2026 Data (raw)** | `fdp/data/raw/openelections/2026/` | Original CSV from conversion |
| **2026 Data (parquet)** | `fdp/data/repos/main/fdga/` | Canonical model (facts, contests, etc.) |
| **Story Bundle** | `public/data/story.json` | Static JSON for frontend apps |
| **XRAY story.json** | `fair-districts-xray/public/data/story.json` | Copy for XRAY app |

### Public Apps That Will Auto-Update

Once you push the certified story.json, these apps will automatically load 2026:

1. **fdex** (Georgia Explorer)
   - URL: https://evolvedhow.github.io/fdex/
   - Needs rebuild to pick up new story.json

2. **lrdb** (Local Redistricting Database)
   - URL: https://evolvedhow.github.io/lrdb/
   - Needs rebuild to pick up new story.json

3. **map-compare** (Plan Comparison)
   - URL: https://evolvedhow.github.io/map-compare/
   - Needs rebuild to pick up new story.json

4. **fdensemble** (Ensemble Benchmark)
   - URL: https://evolvedhow.github.io/fdga-chain/
   - Needs rebuild to pick up new story.json

### Apps That Show Uncertified Data (For Testing)

- **fair-districts-xray** (FairDistricts-XRAY)
  - URL: Local dev only
  - Shows all data including 2026 (uncertified during development)

---

## Part 4: Troubleshooting

### 2026 Doesn't Appear After Certification

**Issue:** You updated the flag but 2026 still doesn't show in public apps.

**Solution:**
1. Verify you changed `certified=False` → `certified=True` in `sources.py`
2. Re-run `build_fdga_cdm.py` (check for errors)
3. Re-run `export_story_data.py` (check for errors)
4. Verify 2026 is in `public/data/story.json` (use Check 1 above)
5. Rebuild each public app with `npm run build`

### Parquet Build Fails

**Issue:** `build_fdga_cdm.py` exits with error.

**Solution:**
1. Check that 2026 CSV exists: `ls fdp/data/raw/openelections/openelections-data-ga-master/2026/`
2. Check for formatting issues in the CSV (invalid values, extra columns)
3. Review the build output for specific error messages

### Story.json Export Fails

**Issue:** `export_story_data.py` doesn't complete.

**Solution:**
1. Ensure parquets were built successfully
2. Check that `duckdb` is available in `.venv`
3. Verify file permissions on output directory

---

## Part 5: Rollback (If Needed)

If something goes wrong and you need to rollback:

### Rollback to Uncertified (Re-Hide 2026)

```bash
cd ~/codebox/fgdp/fdp

# Change in sources.py: certified=True → certified=False
# Then rebuild and export:
.venv/bin/python scripts/build_fdga_cdm.py
.venv/bin/python ../scripts/export_story_data.py

# Commit rollback
git add -A
git commit -m "revert: Rollback 2026 certification (uncertified pending recount)"
git push origin main
```

### Complete Rollback to Last Certified State

```bash
cd ~/codebox/fgdp

# Reset to last known-good commit (before 2026 certification)
git log --oneline | head -20
git reset --hard <commit-hash>  # Use commit before certification changes
git push origin main --force
```

---

## Part 6: Timeline

| Date | Action | Status |
|------|--------|--------|
| Nov 5, 2026 | Election Day | ✅ Completed |
| Nov 6-13, 2026 | Audit Period | In progress |
| Nov 14, 2026 | GA SOS Certification (expected) | Pending |
| After Certification | Update flag + rebuild + export | **← YOU ARE HERE** |
| Within 1 hour | Public apps show 2026 | Target |

---

## Part 7: Quick Reference Commands

### All-in-one certification update (copy & paste):

```bash
# 1. Update sources.py (manually - change certified=False to certified=True)
cd ~/codebox/fgdp/fdp

# 2. Rebuild
.venv/bin/python scripts/build_fdga_cdm.py

# 3. Export
.venv/bin/python ../scripts/export_story_data.py

# 4. Copy to XRAY
cp ~/codebox/fgdp/public/data/story.json \
   ~/codebox/fgdp/fair-districts-xray/public/data/story.json

# 5. Commit and push
cd ~/codebox/fgdp
git add -A
git commit -m "feat: Mark 2026 as certified by GA SOS"
git push origin main

cd ~/codebox/fgdp/fair-districts-xray
git add public/data/story.json
git commit -m "data: Update story.json with certified 2026"
git push origin main

# 6. Rebuild public apps
cd ~/codebox/fgdp/fdex && npm run build
cd ~/codebox/fgdp/lrdb && npm run build
cd ~/codebox/fgdp/map-compare && npm run build
cd ~/codebox/fgdp/fdensemble && npm run build

echo "✅ All done! 2026 is now certified and live."
```

---

## Part 8: Contact & Questions

If you have questions when deploying:

1. Check the `ELECTION_ANALYSIS_2026.md` for data details
2. Check the `IMPLEMENTATION_GUIDE.md` for architecture details
3. Review the parquet file structure: `fdp/fdp/cdm/schema.py`

---

## Summary

**When GA SOS certifies:** 
- Change one flag in `sources.py`
- Run two build scripts
- Push to GitHub
- Public apps automatically get 2026

**Total time:** ~10 minutes  
**Risk:** Minimal (rollback available if needed)  
**Success indicators:** 2026 appears in all app dropdowns

---

**Document Version:** 1.0  
**Last Updated:** November 15, 2026  
**Next Review:** When GA SOS announces certification date
