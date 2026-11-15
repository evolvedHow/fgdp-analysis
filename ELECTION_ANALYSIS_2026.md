# Georgia 2026 Election Results Analysis
## Uncertified Voting Data Preliminary Report

**Generated:** November 15, 2026  
**Data Source:** `requirements/ElectionVotResults-2026-Uncertified.xlsx`  
**Status:** UNCERTIFIED

---

## Executive Summary

The Georgia 2026 election results file contains **comprehensive voting data** across all levels of elections (federal, state, and local). The data is currently marked as **uncertified** and requires schema enhancement to track certification status.

### Key Metrics

| Metric | Value |
|--------|-------|
| **Total Votes Cast** | 140,598,652 |
| **Contests** | 273 |
| **Counties with Data** | 159 |
| **Data Rows** | 11,863 |
| **Certification Status** | ⚠️ UNCERTIFIED |

---

## Data Structure Analysis

### Three Tier Data Organization

#### 1. **Total Votes Sheet** (730 rows)
**Purpose:** Summary-level results by office and party

| Column | Data Type | Content |
|--------|-----------|---------|
| Office Name | String | Election office/race (e.g., "US Senate", "Governor") |
| Contest ID | String | Unique contest identifier |
| Ballot Name | String | Candidate/option name |
| Choice ID | Float64 | Contest-specific choice identifier |
| Party | String | Rep/Dem/Ind/Third party (nullable for totals) |
| **Total** | Integer | Vote count |

**Sample Data:**
- US Senate (Contest US2): 4,182,701 total votes
- Governor (Contest S1): 4,184,814 total votes

#### 2. **Total Votes by Group Sheet** (2,920 rows)
**Purpose:** Voting method breakdown

| Column | Additional Info |
|--------|-----------------|
| All columns from above + | |
| **Group** | Voting method (Election Day, Advance Voting, Absentee by Mail, Provisional) |

**Voting Method Distribution:**
```
Election Day:        45,638,456 votes (32.4%)
Advance Voting:      90,350,450 votes (64.3%)
Absentee by Mail:     4,543,576 votes (3.2%)
Provisional:             66,170 votes (0.05%)
─────────────────────────────────
TOTAL:              140,598,652 votes
```

#### 3. **County Results Sheet** (11,863 rows)
**Purpose:** Detailed county-level breakdown by contest

| Column | Details |
|--------|---------|
| County | 159 Georgia counties |
| Office Name | 273 different contests |
| Contest ID | Unique contest identifier |
| Ballot Name | Candidate/option name |
| Choice ID | Contest-specific choice identifier |
| Party | Political affiliation |
| Total | Vote count |

---

## Coverage Analysis

### Contest Types Included (273 total)
- **Statewide (10):** US Senate, Governor, Lt. Governor, Secretary of State, Attorney General, etc.
- **U.S. House (14):** All GA Congressional districts
- **State Senate (56):** All GA State Senate districts
- **State House (180):** All GA House districts
- **Judicial (9):** District Attorney positions
- **Ballot Measures (3):** Proposed Constitutional Amendments

### County Coverage
✅ All 159 Georgia counties represented

---

## Data Quality Observations

### Strengths
✅ **Complete contest coverage** — all 273 races included  
✅ **Multi-level breakdown** — state, county, and voting method detail  
✅ **Consistent structure** — well-organized across all sheets  
✅ **Full county representation** — 159/159 counties included  

### Current Limitations
⚠️ **Certification status not tracked** — entire dataset marked "uncertified"  
⚠️ **No timestamp** — no audit trail or update timestamps  
⚠️ **No source attribution** — no indication of data source/version  
⚠️ **No reconciliation flags** — can't identify which races are pending audit  

---

## Proposed Schema Enhancement

### Add `certification_status` Attribute

**Add the following columns to enable certification tracking:**

```yaml
certification_fields:
  - name: certification_status
    type: enum
    values: [uncertified, certified, certified_with_caveats]
    description: "Current certification status of the vote count"
    nullable: false
    default: "uncertified"

  - name: certified_date
    type: date
    description: "Date when results were officially certified"
    nullable: true

  - name: certified_by
    type: string
    description: "Official/entity that certified the results"
    nullable: true

  - name: audit_status
    type: enum
    values: [pending, in_progress, complete, flagged]
    description: "Status of any ongoing audit or recount"
    nullable: true
    default: "pending"

  - name: caveat_notes
    type: string
    description: "Any notes or caveats about this record"
    nullable: true
```

### Implementation Strategy

#### Phase 1: Schema Definition
1. Extend `fdp/config/schema/elections.yml` with new fields
2. Update `ElectionLoader` to validate certification fields
3. Add migration script for existing uncertified data

#### Phase 2: Data Model Update
```python
# fdp/schema/models.py - add new dataclass
@dataclass
class ElectionResult:
    county: str
    office_name: str
    contest_id: str
    ballot_name: str
    choice_id: float | None
    party: str | None
    total: int
    
    # NEW CERTIFICATION FIELDS
    certification_status: Literal["uncertified", "certified", "certified_with_caveats"]
    certified_date: str | None = None
    certified_by: str | None = None
    audit_status: Literal["pending", "in_progress", "complete", "flagged"] | None = None
    caveat_notes: str | None = None
```

#### Phase 3: Data Migration
```python
# Map uncertified results
df['certification_status'] = 'uncertified'
df['certified_date'] = None
df['certified_by'] = None
df['audit_status'] = 'pending'  # until official certification
df['caveat_notes'] = None
```

---

## Recommended Next Steps

### Immediate Actions (Week 1)
- [ ] Define official certification status workflow with GA SOS
- [ ] Create mapping of which races are pending certification
- [ ] Set up automated tracking of certification updates
- [ ] Define certification data source/import process

### Short-term (Weeks 2-4)
- [ ] Implement schema changes in fdp
- [ ] Migrate current uncertified data with proper metadata
- [ ] Build certification status tracking dashboard
- [ ] Create certified/uncertified data export workflows

### Long-term (Month 2+)
- [ ] Integrate with GA Secretary of State certification API (if available)
- [ ] Implement automated certification status updates
- [ ] Create audit trail and historical versioning
- [ ] Build reconciliation reporting for certified vs. uncertified changes

---

## File Information

**File Location:** `~/codebox/fgdp/requirements/ElectionVotResults-2026-Uncertified.xlsx`

**File Details:**
- Format: Excel (.xlsx)
- Sheet Count: 3
- Total Data Rows: 12,650 (excluding headers)
- Size: ~500 KB estimated

**Sheets:**
1. Total Votes (730 rows)
2. Total Votes by Group (2,920 rows)
3. County Results (11,863 rows)

---

## Usage in FDP

### Current Structure
```python
from fdp.loaders.elections import ElectionLoader

loader = ElectionLoader(repo)
elections_df = loader.load("elections")  # From dim_elections.parquet
```

### Proposed Post-Enhancement
```python
from fdp.loaders.elections import ElectionLoader, CertificationStatus

loader = ElectionLoader(repo)
elections_df = loader.load("elections")

# Filter for certified results only
certified = elections_df[
    elections_df['certification_status'] == 'certified'
]

# Show uncertified races
uncertified = elections_df[
    elections_df['certification_status'] == 'uncertified'
]
```

---

## Appendix: Contest Breakdown

### Statewide Elections (10)
- US Senate
- Governor
- Lieutenant Governor
- Secretary of State
- Attorney General
- Commissioner of Agriculture
- Commissioner of Insurance
- State School Superintendent
- Commissioner of Labor
- PSC (2 districts: 3, 5)

### Federal Elections (14)
- US House: Districts 1-14 (all districts)

### State Legislative (236)
- State Senate: 56 districts
- State House: 180 districts

### Judicial (9)
- District Attorney (9 circuits)

### Ballot Measures (3)
- Proposed Constitutional Amendment 1
- Proposed Constitutional Amendment 2
- Proposed Constitutional Amendment 3

---

**Report Status:** PRELIMINARY  
**Next Review:** Upon implementation of certification tracking  
**Contact:** FDP Team
