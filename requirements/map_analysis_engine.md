Absolutely. I would design this as a **reusable Election Geography & Partisan Impact Analysis Engine**, exposed through FastAPI, rather than building a Georgia-specific election analysis application.

The key architectural decision is that the engine should treat **election results, district maps, partisan-lean models, and analytical assumptions as independent datasets**. You should be able to combine them in different ways without modifying the underlying data.

For example, you should eventually be able to:

- Compare the 2022 Georgia district map against the 2024 map using the same election results.
- Compare the 2024 map against a proposed redistricting plan.
- Compare two states, two legislative chambers, or two different map generations.
- Apply a statewide political swing of D+5, D+10, or R+5 and see how the seat distribution changes.
- Compare historical partisan lean against actual results.
- Identify districts that became unexpectedly competitive or flipped.
- Determine whether a map continues to provide a structural partisan advantage despite a major statewide political shift.

I would build this around five independent capabilities:

1. **Map Registry** – manage district maps, versions, boundaries, and crosswalks.
2. **Election Data Engine** – manage election cycles, contests, candidates, and results.
3. **Partisan Baseline Engine** – calculate or import historical district lean.
4. **Analytical Engine** – perform map comparisons, swing adjustments, deviations, and simulations.
5. **Visualization/API Layer** – expose analytical results in a format suitable for dashboards, maps, and reports.

Below is a comprehensive functional and technical specification that you can hand to a coding agent.

# Election Geography & Partisan Impact Analysis Engine

## Functional and Technical Specification

**Version:** 1.0\
**Primary implementation:** Python / FastAPI\
**Purpose:** A configurable analytical engine for comparing electoral district maps, measuring partisan movement, evaluating district responsiveness to statewide political swings, and understanding how map boundaries translate votes into legislative seats.

---

# 1. Product Objectives

## 1.1 Primary objective

Build a reusable analytical service that evaluates the relationship between:

- Electoral geography (district maps and boundaries).
- Historical partisan lean.
- Actual election results.
- Statewide political movement.
- District-level political movement.
- Legislative seat distribution.

The service must support comparisons between any two district map versions, including maps from different years, proposed redistricting plans, and alternative hypothetical maps.

The engine must not assume that Georgia, any particular state, or any particular legislative chamber is the only supported geography.

## 1.2 Core analytical questions

The service should answer the following questions.

### A. District behavior

1. Did historically competitive districts become landslides?
2. Did historically safe districts become competitive?
3. Did historically safe districts flip?
4. Which districts resisted the statewide political movement?
5. Which districts moved more or less than the statewide swing would predict?

### B. Map effectiveness

1. How does a particular map translate votes into seats?
2. Does one map provide a structural advantage to a particular party?
3. How many seats change when the same election results are applied to two different maps?
4. How many districts are genuinely competitive?
5. How does the seat distribution change under different statewide political environments?

### C. Historical and geographic behavior

1. Are political shifts consistent across districts?
2. Are there regional patterns?
3. Are some types of districts more responsive to statewide movement?
4. Are political changes concentrated in suburban, urban, or rural districts?
5. Does a new map materially alter the relationship between voter preferences and legislative representation?

## 1.3 Design principles

- Geography must be independent of election data.
- Election results must be independent of map versions.
- Historical partisan lean must be independently configurable.
- All calculations must be reproducible.
- Analytical assumptions must be explicit and versioned.
- Every analysis must preserve its inputs and parameters.
- The system must support multiple parties, not just Democrats and Republicans.
- Calculations must use actual vote totals wherever possible, not averages of percentages.
- The same analysis must be executable through an API or a scheduled batch process.
- No analytical result should silently mix incompatible geographies or election types.

---

# 2. Fundamental Architecture

The system should have five primary functional modules.

| Module            | Responsibility                                                       |
| ----------------- | -------------------------------------------------------------------- |
| Map Registry      | Stores maps, boundaries, versions, and geographic relationships      |
| Election Registry | Stores elections, contests, candidates, and vote totals              |
| Partisan Baseline | Stores historical lean and district classifications                  |
| Analysis Engine   | Executes comparisons, swing adjustments, simulations, and statistics |
| Results API       | Provides structured outputs, maps, charts, and downloadable datasets |

The analytical engine should be stateless wherever practical. All inputs should be explicitly provided or referenced by immutable dataset/version identifiers.

## 2.1 Important distinction: Two types of map comparisons

The application must distinguish two fundamentally different analyses.

**Mode 1: Structural map comparison**

Apply the SAME election results to Map A and Map B.

This isolates the impact of changing district boundaries while holding the election and political environment constant.

Example:

- Map A: Georgia 2021 congressional map.
- Map B: Georgia proposed alternative congressional map.
- Election: 2024 congressional election.
- Question: How would the same underlying votes translate into seats under each map?

This is the strongest way to isolate the effects of district design.

**Mode 2: Historical election comparison**

Compare election results occurring under different maps and potentially different political environments.

Example:

- Map A: Georgia 2022 map.
- Election A: 2022.
- Map B: Georgia 2024 map.
- Election B: 2024.

This shows what actually happened but combines several effects:

- Changes in district boundaries.
- Changes in statewide political preferences.
- Changes in voter participation.
- Candidate-specific effects.
- Changes in the electorate.

The engine must never present this comparison as a pure map effect.

**Mode 3: Counterfactual political environment**

Apply hypothetical statewide political swings to a selected map and election baseline.

Example:

- 2024 election baseline.
- 2024 district map.
- Simulated Democratic swing: +5, +10, +15 points.
- Simulated Republican swing: +5 points.

Calculate the resulting district winners and legislative seat distribution.

All three modes should share the same analytical infrastructure.

---

# 3. Map Registry

## 3.1 Purpose

Maintain a registry of electoral maps and their boundaries.

A map is a named, versioned collection of districts.

Examples:

- Georgia State House 2021.
- Georgia State Senate 2021.
- Georgia Congressional 2021.
- Georgia State House proposed 2027.
- Georgia State Senate proposed alternative A.

## 3.2 Map metadata

Each map should contain:

| Field            | Description                                 |
| ---------------- | ------------------------------------------- |
| map_id           | Unique identifier                           |
| map_name         | Human-readable name                         |
| jurisdiction     | Country, state, or other jurisdiction       |
| state_code       | Standard state identifier                   |
| chamber          | House, Senate, Congressional, Council, etc. |
| map_version      | Version or adoption year                    |
| effective_start  | Effective date                              |
| effective_end    | End date, if applicable                     |
| total_districts  | Number of districts                         |
| geographic_level | State, county, municipal, etc.              |
| boundary_source  | Source of geographic data                   |
| boundary_vintage | Geographic boundary vintage                 |
| status           | Draft, proposed, enacted, retired           |
| created_at       | Timestamp                                   |
| metadata         | Additional attributes                       |

## 3.3 District metadata

Each district must be individually identifiable.

Fields:

- district_id
- map_id
- district_number
- district_name
- district_geometry
- population, if available
- registered_voters, if available
- voting_age_population, if available
- geographic_area
- demographic_attributes
- metadata

A district's identity must be tied to a particular map version.

District 12 under one map must not automatically be assumed to be geographically equivalent to District 12 under another map.

## 3.4 Geographic representation

Use standard geospatial formats.

Preferred storage:

- PostGIS for spatial geometry.
- GeoJSON for API interchange.
- EPSG:4326 for geographic coordinates.
- Appropriate projected coordinate systems for area calculations.

Store district polygons as multipolygons where necessary.

The engine must support:

- District boundary imports.
- GeoJSON uploads.
- Shapefile imports.
- GeoPackage imports.
- Boundary validation.
- District overlap detection.
- Geographic coverage validation.

## 3.5 Map validation

When a map is registered, validate:

1. All districts have unique identifiers within the map.
2. District polygons are geometrically valid.
3. Districts do not have unintended overlaps.
4. The overall map covers the expected jurisdiction.
5. No significant geographic gaps exist.
6. District count matches the declared count.
7. All geometries use a known coordinate reference system.

Validation results should be stored with the map version.

---

# 4. Geographic Crosswalk Engine

This is one of the most important components.

Different maps have different district boundaries. Historical election results are frequently available at precinct level rather than district level.

The engine must be able to translate election results from their source geography into any supported map.

## 4.1 Supported source geographies

- Precincts.
- Census blocks.
- Census block groups.
- Census tracts.
- Counties.
- Municipalities.
- Existing electoral districts.

## 4.2 Crosswalk methods

Support the following methods:

**A. Direct assignment**

When a precinct or source geography falls entirely within one district, assign its votes directly.

**B. Geographic area weighting**

For source geography intersecting multiple districts, allocate votes based on the proportion of geographic area.

**C. Census block allocation**

Use census blocks to allocate precinct-level results when block-level geographic intersections are available.

**D. Population weighting**

Allocate based on population proportions.

**E. Voting-age population weighting**

Allocate based on voting-age population.

**F. Registered voter weighting**

Allocate based on registered voter distribution, where available.

**G. Custom crosswalk**

Allow users to supply an externally prepared source-to-district allocation table.

## 4.3 Important allocation rules

Never assume that population weighting, area weighting, and voting-age population weighting produce equivalent results.

Each crosswalk must record:

- Source geography.
- Destination map.
- Allocation method.
- Source dataset.
- Weighting dataset.
- Allocation date.
- Geographic vintage.
- Coverage percentage.
- Unallocated vote totals.
- Estimated versus directly assigned vote totals.

Where possible, use actual source-level vote totals and sum allocated votes into districts.

Do not allocate percentages and then average them.

For example:

District Democratic vote share must be calculated as:

Democratic votes in district / Total valid two-party votes in district.

It must not be calculated as the average of precinct Democratic percentages.

## 4.4 Crosswalk confidence

Provide a crosswalk quality score based on:

- Percentage of votes directly assigned.
- Percentage estimated through geographic allocation.
- Percentage of geography successfully matched.
- Missing source geography.
- Availability of population weighting data.

Expose these values in all analytical responses.

The confidence score should be accompanied by its component metrics. Do not imply statistical certainty merely from a high coverage percentage.

---

# 5. Election Registry

## 5.1 Election metadata

Each election must be independently registered.

Fields:

- election_id
- election_name
- jurisdiction
- election_date
- election_year
- election_type
- election_stage
- election_round
- data_source
- data_vintage
- certification_status
- metadata

Election types should include:

- General.
- Primary.
- Special.
- Runoff.
- Presidential.
- Gubernatorial.
- Senate.
- Congressional.
- State legislative.
- Local.

## 5.2 Contest registry

An election can contain multiple contests.

Fields:

- contest_id
- election_id
- office
- chamber
- district_number, if applicable
- contest_geography
- contest_type
- seats_available
- total_ballots
- total_valid_votes
- metadata

Support both single-member and multi-member contests.

## 5.3 Candidate and party data

Fields:

- candidate_id
- candidate_name
- party_id
- party_name
- contest_id
- votes
- vote_share
- incumbent_status
- candidate_metadata

Party identifiers must be configurable.

Do not hardcode Democratic and Republican parties into the data model.

## 5.4 Election result granularity

Support results at multiple levels:

- Statewide contest.
- Congressional district.
- Legislative district.
- County.
- Precinct.
- Other geographic reporting units.

Store raw results at their original reporting geography.

Derived district results should be generated through the Geographic Crosswalk Engine.

Preserve both raw and derived results.

## 5.5 Result normalization

The analytical engine must support:

- Two-party vote share.
- All-party vote share.
- Candidate vote totals.
- Party vote totals.
- Write-in votes.
- Undervotes and overvotes, where available.
- Ballot measures separately from candidate contests.

The default partisan comparison should use a two-party Democratic-versus-Republican margin when both parties are present.

However, all-party results should remain accessible.

---

# 6. Partisan Baseline Engine

## 6.1 Purpose

Represent the expected political lean of each district independently of its actual election outcome.

The baseline may originate from GA Explorer's 2018–24 index or another independently generated partisan model.

The system must support multiple baseline methodologies.

## 6.2 Baseline types

- Imported partisan lean index.
- Historical average partisan performance.
- Composite statewide-election index.
- Presidential performance index.
- Gubernatorial performance index.
- Congressional performance index.
- User-defined weighted index.
- Model-generated partisan lean.

## 6.3 Baseline metadata

Each baseline should include:

- baseline_id
- baseline_name
- baseline_version
- jurisdiction
- chamber
- map_id
- source_elections
- calculation_method
- election_weighting
- normalization_method
- party_orientation
- calculation_date
- description

## 6.4 District baseline values

For each district:

- district_id
- baseline_id
- democratic_lean
- republican_lean
- partisan_margin
- partisan_rating
- confidence
- source_metadata

Use a consistent sign convention:

Positive margin = Democratic advantage.

Negative margin = Republican advantage.

Zero = even.

## 6.5 Historical partisan rating classifications

Allow configurable thresholds.

Default example:

| Partisan margin | Classification    |
| --------------- | ----------------- |
| D+15 or greater | Solid Democratic  |
| D+10 to D+15    | Likely Democratic |
| D+5 to D+10     | Lean Democratic   |
| D+5 to R+5      | Competitive       |
| R+5 to R+10     | Lean Republican   |
| R+10 to R+15    | Likely Republican |
| R+15 or greater | Solid Republican  |

These thresholds must be configurable by analysis.

Store the continuous numerical margin as the authoritative value. Ratings are derived classifications, not independent measurements.

## 6.6 Baseline compatibility

A baseline must be associated with a specific map or geographic vintage.

If a baseline is defined on Map A and the user wants to analyze Map B, the engine must either:

1. Recalculate the baseline using underlying source-election results on Map B; or
2. Use an explicitly supplied crosswalk to transfer the baseline.

Do not blindly transfer district-level lean from one map to another.

This is critical when comparing alternative maps.

---

# 7. Analytical Engine

The analytical engine is the core of the application.

It should expose independent calculation functions that can be combined into larger analyses.

All calculations must return both the result and the assumptions used.

## 7.1 Standardized partisan margin

Use a common margin convention throughout the engine.

For a two-party contest:

Democratic margin = Democratic vote share - Republican vote share.

For example:

- D+10 = +10.
- R+10 = -10.
- Even = 0.

Use percentage points, not percentage changes.

Store both:

- Democratic vote share.
- Republican vote share.
- Democratic margin.

## 7.2 Statewide political swing

Calculate statewide movement between two comparable election benchmarks.

Formula:

Statewide Swing = Current Democratic Margin - Previous Democratic Margin.

Example:

Previous election:

- Democratic share: 48%.
- Republican share: 52%.
- Margin: -4.

Current election:

- Democratic share: 58%.
- Republican share: 42%.
- Margin: +16.

Statewide swing = +20 percentage points.

Important: A change from R+4 to D+16 is a 20-point swing, not a 10-point swing.

Support multiple statewide swing benchmarks:

- Presidential.
- Gubernatorial.
- Senate.
- Congressional aggregate.
- User-selected contest.
- Weighted composite.

The user must be able to specify which benchmark to use.

## 7.3 Expected district performance

Calculate the expected district result after applying statewide movement to the historical partisan baseline.

Formula:

Expected District Margin = Historical District Lean + Statewide Swing.

Example:

Historical district lean = R+12 = -12.

Statewide swing = D+10 = +10.

Expected district margin = -2, or R+2.

This is the simple uniform-swing model.

The engine must label this as a uniform swing assumption, not a prediction with guaranteed accuracy.

## 7.4 Actual district performance

Calculate actual district margins from election results aggregated onto the selected map.

Example:

Actual result = D+5.

## 7.5 District deviation

This is the primary metric for measuring whether districts behaved as expected.

Formula:

District Deviation = Actual District Margin - Expected District Margin.

Example:

Expected result = R+2 = -2.

Actual result = D+5 = +5.

Deviation = +7.

Interpretation: The district performed seven points more Democratic than the uniform-swing model expected.

Negative deviation indicates Republican overperformance relative to expectation.

Positive deviation indicates Democratic overperformance relative to expectation.

## 7.6 District classifications

Support four primary classifications.

A. Competitive districts that became landslides.

B. Historically safe districts that became competitive.

C. Historically safe districts that flipped.

D. Districts that resisted the statewide swing.

These classifications should be configurable through thresholds.

Recommended classification logic:

- Historical competitiveness determined from baseline margin.
- Actual competitiveness determined from actual election margin.
- Flip determined by a change in winning party.
- Resistance determined by the sign and magnitude of deviation.

Avoid treating all districts with a large deviation as the same type of event.

A district can be a flip and also have a large deviation. Preserve both the primary category and all applicable secondary flags.

## 7.7 Statistical summary

Calculate:

- Number of districts analyzed.
- Number of districts won by each party.
- Average deviation.
- Median deviation.
- Standard deviation.
- Minimum deviation.
- Maximum deviation.
- Mean absolute deviation.
- Number of districts with positive deviation.
- Number of districts with negative deviation.
- Number of districts within a configurable deviation threshold.
- Number of unexpected flips.
- Number of unexpectedly competitive districts.

Calculate these independently for each chamber.

## 7.8 Distribution of district responsiveness

Create configurable deviation bands.

Example:

| Deviation        | Classification                      |
| ---------------- | ----------------------------------- |
| Greater than +10 | Strong Democratic overperformance   |
| +5 to +10        | Moderate Democratic overperformance |
| -5 to +5         | Approximately expected              |
| -10 to -5        | Moderate Republican overperformance |
| Less than -10    | Strong Republican overperformance   |

The thresholds must be configurable.

Provide district counts and percentages for each category.

---

# 8. Map Comparison Engine

## 8.1 Purpose

Compare two different map versions using a common election baseline.

The comparison should evaluate how different geographic boundaries affect:

- District-level partisan composition.
- District competitiveness.
- Winning party.
- Seat allocation.
- Partisan advantage.
- Geographic representation.

## 8.2 Required comparison inputs

- Map A ID.
- Map B ID.
- Election ID.
- Election contest type.
- Source election geography.
- Crosswalk method.
- Party configuration.
- Optional partisan baseline.
- Optional analysis parameters.

## 8.3 Same-election comparison

This is the preferred structural comparison.

Take the same election results and independently aggregate them to Map A and Map B.

Calculate for each map:

- District vote totals.
- Democratic vote share.
- Republican vote share.
- District partisan margin.
- District winner.
- District competitiveness.
- Total seats won by each party.
- Seat share.
- Average district partisan margin.

Then compare:

- Seats gained or lost under Map B.
- Districts whose partisan winner changes.
- Changes in district competitiveness.
- Changes in the number of safe seats.
- Changes in the number of competitive seats.
- Changes in partisan advantage.

## 8.4 District correspondence

District 1 under Map A may overlap several districts under Map B.

Therefore, do not compare districts by their numeric identifiers.

Instead, generate a geographic correspondence table.

Include:

- Map A district.
- Map B district.
- Geographic overlap.
- Population overlap.
- Voting-age population overlap.
- Registered voter overlap, if available.
- Source allocation methodology.

This allows the system to identify which districts were split, combined, or substantially reconfigured.

## 8.5 Historical map comparison

Support comparing different map/election combinations.

Example:

Map A + Election A versus Map B + Election B.

Return the observed difference, but explicitly identify that map and election effects are combined.

Where possible, provide an additional same-election comparison to isolate the structural map effect.

## 8.6 Map impact summary

For each comparison:

- Party seat distribution under Map A.
- Party seat distribution under Map B.
- Seat-share difference.
- Number of districts changing winner.
- Number of districts changing competitiveness classification.
- Number of districts substantially reconfigured.
- Geographic concentration of partisan changes.

---

# 9. Seat Conversion and Partisan Advantage

## 9.1 Vote share versus seat share

Calculate:

- Statewide Democratic vote share.
- Aggregate district Democratic vote share.
- Democratic seat share.
- Republican seat share.
- Difference between vote share and seat share.

Important: Show statewide vote share and aggregate legislative district vote share separately. They are not necessarily equivalent.

## 9.2 Seat conversion efficiency

Measure the relationship between votes and seats.

Calculate:

Seat Conversion Ratio = Party Seat Share / Party District Vote Share.

This is a descriptive metric, not a standalone measure of gerrymandering.

Also report the raw difference:

Seat Share Gap = Party Seat Share - Party District Vote Share.

## 9.3 Competitive district distribution

Calculate the number of districts within:

- 1 percentage point.
- 3 percentage points.
- 5 percentage points.
- 10 percentage points.
- 15 percentage points.

Make these thresholds configurable.

Provide both district counts and percentages.

## 9.4 Partisan symmetry and efficiency metrics

Include optional advanced measures:

**A. Efficiency gap**

Estimate the difference in wasted votes between parties.

**B. Mean-median difference**

Compare the statewide median district vote share with the mean district vote share.

**C. Partisan bias**

Estimate seat outcomes for both parties at a hypothetical 50% district vote share under the chosen model.

**D. Seats-votes curve**

Show how legislative seat allocation changes as statewide or aggregate district vote share changes.

All metrics must disclose their mathematical assumptions and limitations.

Do not treat any single metric as definitive evidence of intentional partisan gerrymandering.

---

# 10. Political Swing Simulation Engine

## 10.1 Purpose

Allow users to apply hypothetical political shifts to a map and estimate resulting district outcomes.

This is a key capability and should be implemented independently from actual election analysis.

## 10.2 Simulation parameters

- map_id
- baseline_election_id
- baseline_map_id
- baseline_method
- swing_party
- swing_amount
- swing_method
- responsiveness_model
- district_adjustment
- turnout_assumption
- simulation_name

## 10.3 Uniform swing simulation

Default method:

Simulated District Margin = Baseline District Margin + Statewide Swing.

Example:

| District | Baseline | Simulated D+10 |
| -------- | -------- | -------------- |
| A        | D+15     | D+25           |
| B        | D+5      | D+15           |
| C        | R+5      | D+5            |
| D        | R+15     | R+5            |
| E        | R+25     | R+15           |

Recalculate:

- District winners.
- Seats won.
- Seat share.
- Competitive districts.
- Flipped districts.
- Partisan advantage.

## 10.4 Non-uniform swing simulation

Support more sophisticated methods.

**A. Regional swing**

Apply different swings to different regions.

**B. Historical responsiveness**

Estimate district-specific responsiveness based on historical election results.

**C. Demographic responsiveness**

Allow optional models using district demographic attributes.

**D. User-defined district adjustments**

Allow explicit district-level overrides.

**E. Hybrid model**

Combine statewide swing, regional movement, historical responsiveness, and district-specific adjustments.

All adjustments must be visible in the analysis configuration.

## 10.5 Seat response curve

Generate a series of simulations across a range of statewide swings.

Example:

- R+15.
- R+10.
- R+5.
- Even.
- D+5.
- D+10.
- D+15.
- D+20.

For each scenario, return:

- Democratic seats.
- Republican seats.
- Other-party seats.
- Competitive seats.
- Seat share.
- Number of flipped districts.

The output should support charting the relationship between statewide vote share and legislative seats.

## 10.6 Important distinction

A uniform swing simulation is a deterministic scenario, not a probabilistic election forecast.

A future enhancement may introduce uncertainty ranges and Monte Carlo simulations.

---

# 11. Geographic and Regional Analysis

## 11.1 Regional classification

Support user-defined regions.

Examples:

- Metro Atlanta.
- North Georgia.
- Central Georgia.
- South Georgia.
- Coastal Georgia.
- Rural Georgia.
- Suburban Georgia.
- Urban Georgia.

Regions may be defined using:

- Counties.
- ZIP codes.
- Census geography.
- User-uploaded polygons.
- Custom district groupings.

## 11.2 Regional statistics

For each region, calculate:

- Historical partisan lean.
- Actual partisan margin.
- Statewide swing.
- Regional swing.
- Average district deviation.
- Median district deviation.
- Number of districts flipped.
- Number of competitive districts.
- Seat distribution.

## 11.3 Geographic outliers

Identify districts with unusually high or low deviations.

Allow ranking by:

- Largest Democratic overperformance.
- Largest Republican overperformance.
- Largest change from historical lean.
- Largest margin change.
- Most unexpected partisan flip.

## 11.4 Optional demographic analysis

Support demographic attributes as independent geographic datasets.

Potential variables:

- Race and ethnicity.
- Age.
- Educational attainment.
- Income.
- Urbanization.
- Population density.
- Homeownership.
- Employment.

These should be optional explanatory variables, not required inputs.

Avoid making causal claims based solely on demographic correlations.

---

# 12. Analysis Configuration

All analytical parameters should be configurable through a single analysis request.

## 12.1 Required configuration groups

### Geography

- Jurisdiction.
- Chamber.
- Map A.
- Map B.
- Geographic vintage.

### Election selection

- Election A.
- Election B.
- Election benchmark.
- Contest type.
- Election stage.

### Partisan baseline

- Baseline ID.
- Baseline version.
- Calculation methodology.
- Party orientation.

### Swing assumptions

- Statewide benchmark.
- Swing magnitude.
- Swing direction.
- Swing calculation method.
- Uniform or non-uniform swing.

### Classification

- Competitive thresholds.
- Safe-seat thresholds.
- Unexpected movement thresholds.
- Flip definitions.

### Crosswalk

- Allocation methodology.
- Weighting dataset.
- Minimum coverage threshold.
- Missing data treatment.

### Output

- District detail.
- Summary statistics.
- Geographic analysis.
- Seat conversion.
- Seat response curve.
- GeoJSON.
- CSV.
- Chart-ready series.

## 12.2 Analysis presets

Support named, reusable configurations.

Examples:

- Georgia 2022 versus 2024.
- Georgia 2024 historical partisan response.
- Georgia 2024 proposed map comparison.
- Uniform D+10 simulation.
- Uniform R+5 simulation.
- Metro Atlanta regional analysis.

Presets should reference dataset versions, not duplicate the underlying data.

---

# 13. FastAPI Interface Specification

Use REST endpoints with Pydantic request and response models.

All endpoints should be versioned under `/api/v1`.

## 13.1 Map endpoints

| Method | Endpoint                        | Purpose                      |
| ------ | ------------------------------- | ---------------------------- |
| POST   | /maps                           | Register a map               |
| GET    | /maps                           | List maps                    |
| GET    | /maps/{map_id}                  | Retrieve map metadata        |
| PUT    | /maps/{map_id}                  | Update metadata              |
| POST   | /maps/{map_id}/districts/import | Import district boundaries   |
| GET    | /maps/{map_id}/districts        | List districts               |
| GET    | /maps/{map_id}/geojson          | Retrieve district geometries |
| POST   | /maps/{map_id}/validate         | Validate map                 |

## 13.2 Crosswalk endpoints

| Method | Endpoint                  | Purpose                  |
| ------ | ------------------------- | ------------------------ |
| POST   | /crosswalks               | Create a crosswalk       |
| GET    | /crosswalks               | List crosswalks          |
| GET    | /crosswalks/{id}          | Retrieve crosswalk       |
| POST   | /crosswalks/{id}/validate | Validate allocation      |
| GET    | /crosswalks/{id}/quality  | Retrieve quality metrics |

## 13.3 Election endpoints

| Method | Endpoint                       | Purpose                    |
| ------ | ------------------------------ | -------------------------- |
| POST   | /elections                     | Register election          |
| GET    | /elections                     | List elections             |
| GET    | /elections/{id}                | Retrieve election          |
| POST   | /elections/{id}/results/import | Import results             |
| GET    | /elections/{id}/contests       | List contests              |
| GET    | /elections/{id}/results        | Retrieve results           |
| POST   | /elections/{id}/aggregate      | Aggregate results to a map |

## 13.4 Baseline endpoints

| Method | Endpoint                  | Purpose                                |
| ------ | ------------------------- | -------------------------------------- |
| POST   | /baselines                | Register baseline                      |
| GET    | /baselines                | List baselines                         |
| GET    | /baselines/{id}           | Retrieve baseline                      |
| POST   | /baselines/{id}/calculate | Calculate baseline                     |
| POST   | /baselines/{id}/transfer  | Transfer baseline to another geography |
| GET    | /baselines/{id}/districts | Retrieve district lean                 |

## 13.5 Analysis endpoints

| Method | Endpoint                          | Purpose                                |
| ------ | --------------------------------- | -------------------------------------- |
| POST   | /analysis/district-response       | Expected versus actual analysis        |
| POST   | /analysis/map-comparison          | Compare two maps                       |
| POST   | /analysis/historical-comparison   | Compare two election periods           |
| POST   | /analysis/swing                   | Calculate statewide and regional swing |
| POST   | /analysis/simulation              | Run political swing simulation         |
| POST   | /analysis/seat-curve              | Generate seat response curve           |
| POST   | /analysis/partisan-metrics        | Calculate partisan advantage metrics   |
| POST   | /analysis/regional                | Run regional analysis                  |
| POST   | /analysis/outliers                | Identify district outliers             |
| GET    | /analysis/{analysis_id}           | Retrieve analysis                      |
| GET    | /analysis/{analysis_id}/districts | Retrieve district results              |
| GET    | /analysis/{analysis_id}/geojson   | Retrieve results with geometries       |
| GET    | /analysis/{analysis_id}/export    | Export results                         |

## 13.6 General endpoints

- `GET /health`
- `GET /version`
- `GET /metadata/parties`
- `GET /metadata/classifications`
- `GET /metadata/analysis-methods`

---

# 14. Example API Requests

## 14.1 District response analysis

Endpoint:

`POST /api/v1/analysis/district-response`

Example request:

```
{
  "jurisdiction": "US-GA",
  "chamber": "state_house",
  "map_id": "ga_house_2021",
  "election_id": "ga_general_2026",
  "baseline_id": "ga_explorer_2018_2024",
  "statewide_benchmark": {
    "election_id": "ga_general_2026",
    "contest_type": "governor"
  },
  "swing_method": "uniform",
  "classification": {
    "competitive_threshold": 5,
    "safe_threshold": 15,
    "unexpected_deviation_threshold": 5
  },
  "party_configuration": {
    "reference_party": "DEM",
    "opposition_party": "REP"
  },
  "include": {
    "districts": true,
    "summary": true,
    "regional": true,
    "outliers": true
  }
}
```

## 14.2 Map comparison

Endpoint:

`POST /api/v1/analysis/map-comparison`

Example request:

```
{
  "comparison_mode": "structural_same_election",
  "map_a": {
    "map_id": "ga_house_2021"
  },
  "map_b": {
    "map_id": "ga_house_proposed_2027"
  },
  "election": {
    "election_id": "ga_general_2026",
    "contest_type": "state_house"
  },
  "crosswalk": {
    "method": "census_block",
    "minimum_coverage": 0.98
  },
  "party_configuration": {
    "reference_party": "DEM",
    "opposition_party": "REP"
  },
  "include": {
    "district_comparison": true,
    "seat_distribution": true,
    "competitiveness": true,
    "geographic_correspondence": true,
    "partisan_metrics": true
  }
}
```

## 14.3 Political swing simulation

Endpoint:

`POST /api/v1/analysis/simulation`

Example request:

```
{
  "map_id": "ga_house_2021",
  "baseline_election_id": "ga_general_2026",
  "baseline_map_id": "ga_house_2021",
  "swing_method": "uniform",
  "swing_scenarios": [
    -10,
    -5,
    0,
    5,
    10,
    15
  ],
  "classification": {
    "competitive_threshold": 5,
    "safe_threshold": 15
  },
  "include": {
    "district_results": true,
    "seat_distribution": true,
    "seat_curve": true
  }
}
```

All swing amounts use the reference party's perspective. Positive means movement toward the reference party; negative means movement away from it.

---

# 15. Standard Analysis Response

All analysis endpoints should return a consistent response envelope.

Example:

```
{
  "analysis_id": "analysis_12345",
  "analysis_type": "district_response",
  "status": "completed",
  "created_at": "2026-11-13T12:00:00Z",
  "configuration": {
    "map_id": "ga_house_2021",
    "election_id": "ga_general_2026",
    "baseline_id": "ga_explorer_2018_2024",
    "swing_method": "uniform"
  },
  "summary": {
    "total_districts": 180,
    "democratic_seats": 102,
    "republican_seats": 78,
    "statewide_swing": 10.0,
    "average_deviation": 2.1,
    "median_deviation": 1.4,
    "standard_deviation": 5.8,
    "unexpected_flips": 8,
    "newly_competitive": 14,
    "resistant_districts": 9
  },
  "classification_summary": {},
  "regional_summary": {},
  "outliers": [],
  "district_results": [],
  "data_quality": {},
  "methodology": {}
}
```

The numbers above are illustrative only.

The API must return enough information for a frontend to render charts without needing to recalculate analytical metrics.

---

# 16. District-Level Response Schema

Each district result should include:

```
{
  "district_id": "ga_house_2021_001",
  "district_number": "1",
  "historical_lean": -12.0,
  "historical_rating": "solid_republican",
  "statewide_swing": 10.0,
  "expected_margin": -2.0,
  "actual_margin": 5.0,
  "district_deviation": 7.0,
  "winner": "DEM",
  "historical_winner": "REP",
  "actual_competitiveness": "lean_democratic",
  "primary_classification": "historically_safe_flipped",
  "flags": [
    "unexpected_flip",
    "democratic_overperformance"
  ],
  "democratic_vote_share": 52.5,
  "republican_vote_share": 47.5,
  "democratic_votes": 12500,
  "republican_votes": 11300
}
```

All numerical values must be derived from the underlying datasets and calculations.

---

# 17. Data Model and Persistence

Recommended logical entities:

1. Jurisdiction
2. Map
3. District
4. GeographicSource
5. Crosswalk
6. Election
7. Contest
8. Candidate
9. Party
10. ElectionResult
11. PartisanBaseline
12. BaselineDistrict
13. AnalysisConfiguration
14. AnalysisRun
15. AnalysisDistrictResult
16. AnalysisSummary
17. SimulationScenario
18. Region
19. DistrictRegionRelationship

## 17.1 Data separation

Keep these logically independent:

- Raw election data.
- Geographic boundaries.
- Crosswalks.
- Partisan baselines.
- Derived election results.
- Analytical outputs.

Never overwrite original election data with aggregated results.

## 17.2 Reproducibility

Every analysis must preserve:

- Input dataset identifiers.
- Input dataset versions.
- Map versions.
- Crosswalk version.
- Baseline version.
- Calculation method.
- Configuration parameters.
- Software/model version.
- Creation timestamp.

An analysis must be reproducible using its stored configuration and input versions.

## 17.3 Caching

Cache expensive intermediate calculations:

- Election results aggregated to a map.
- Baseline calculations.
- Geographic crosswalks.
- Map comparison results.

Cache keys must incorporate dataset versions and relevant calculation parameters.

---

# 18. Technical Implementation Recommendations

## 18.1 Suggested stack

| Component              | Technology                          |
| ---------------------- | ----------------------------------- |
| API                    | FastAPI                             |
| Validation             | Pydantic                            |
| ORM                    | SQLAlchemy                          |
| Database               | PostgreSQL                          |
| Geospatial database    | PostGIS                             |
| Data processing        | Pandas / Polars                     |
| Geospatial processing  | GeoPandas / Shapely                 |
| Numerical calculations | NumPy / SciPy                       |
| Background jobs        | Celery or an equivalent task runner |
| Cache                  | Redis                               |
| API documentation      | OpenAPI                             |
| Testing                | Pytest                              |

Keep the analytical calculations in pure Python service functions, independent of FastAPI request handlers.

## 18.2 Suggested project structure

```
election_analysis/
│
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── maps.py
│   │       ├── elections.py
│   │       ├── crosswalks.py
│   │       ├── baselines.py
│   │       └── analysis.py
│   │
│   ├── models/
│   │   ├── map.py
│   │   ├── district.py
│   │   ├── election.py
│   │   ├── contest.py
│   │   ├── results.py
│   │   ├── baseline.py
│   │   └── analysis.py
│   │
│   ├── schemas/
│   │   ├── map.py
│   │   ├── election.py
│   │   ├── baseline.py
│   │   └── analysis.py
│   │
│   ├── services/
│   │   ├── map_service.py
│   │   ├── election_service.py
│   │   ├── crosswalk_service.py
│   │   ├── baseline_service.py
│   │   ├── swing_service.py
│   │   ├── district_service.py
│   │   ├── comparison_service.py
│   │   ├── simulation_service.py
│   │   └── metrics_service.py
│   │
│   ├── analytics/
│   │   ├── margins.py
│   │   ├── swing.py
│   │   ├── deviations.py
│   │   ├── competitiveness.py
│   │   ├── seat_conversion.py
│   │   ├── partisan_metrics.py
│   │   ├── simulations.py
│   │   └── regional.py
│   │
│   ├── repositories/
│   ├── tasks/
│   ├── core/
│   └── utils/
│
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── analytics/
│   └── fixtures/
│
├── scripts/
├── pyproject.toml
└── README.md
```

The structure is illustrative. Avoid introducing unnecessary abstractions or excessive service layers.

---

# 19. Validation and Analytical Safeguards

The system must validate assumptions before executing an analysis.

## 19.1 Geographic validation

- Map A and Map B must belong to compatible jurisdictions for a direct comparison.
- Map versions must be identified explicitly.
- District boundaries must be valid.
- Crosswalk coverage must be reported.
- Geographic vintage mismatches must be flagged.

## 19.2 Election validation

- Election results must be certified or clearly labeled as unofficial.
- Election stages must be compatible.
- Runoffs must not accidentally be combined with general-election results.
- Contests must have compatible party and candidate definitions.
- Missing vote totals must be identified.

## 19.3 Baseline validation

- Baseline must match the selected map or have a valid transfer procedure.
- Baseline source elections must be recorded.
- Historical results must not inadvertently include the election being evaluated.
- Baseline and election periods must be clearly identified.

## 19.4 Swing validation

- The reference party must be consistent.
- Statewide swing must be based on comparable benchmarks.
- The system must distinguish margin changes from vote-share changes.
- A statewide swing benchmark must not be silently substituted when missing.

## 19.5 Interpretation safeguards

Every analysis should disclose:

- Whether the analysis is structural, historical, or counterfactual.
- Whether results are actual or estimated.
- Whether geographic allocations were required.
- Whether the swing model is uniform or non-uniform.
- Whether district responsiveness is estimated.
- Whether the result is descriptive or predictive.

Do not equate correlation with causation.

---

# 20. Performance and Scalability

The engine should be designed to support multiple states and potentially thousands of districts without requiring major architectural changes.

Requirements:

- Vectorized calculations wherever practical.
- Efficient spatial indexing through PostGIS.
- Precomputed crosswalks.
- Cached aggregated election results.
- Background processing for large geographic operations.
- Pagination for district-level API responses.
- Optional GeoJSON simplification for large map responses.
- Configurable job timeouts.
- Idempotent analysis execution.

Small district analyses should execute synchronously when practical.

Large crosswalk creation, map comparisons, and extensive simulations should support asynchronous execution.

For asynchronous execution:

1. Submit analysis.
2. Return analysis ID and status.
3. Execute in background.
4. Expose status endpoint.
5. Retrieve completed results.

---

# 21. Testing Requirements

Testing must cover analytical correctness, not merely API behavior.

## 21.1 Unit tests

Test:

- Margin calculations.
- Statewide swing calculations.
- Expected district margin.
- District deviation.
- District classifications.
- Seat allocation.
- Competitive thresholds.
- Seat response curves.
- Partisan metrics.

## 21.2 Geographic tests

Test:

- District overlap.
- Precinct-to-district assignment.
- Split precinct allocation.
- Population weighting.
- Census block weighting.
- Incomplete geographic coverage.
- Invalid geometries.

## 21.3 Integration tests

Test:

- Register map.
- Import election results.
- Create crosswalk.
- Calculate baseline.
- Execute district response analysis.
- Execute structural map comparison.
- Run political swing simulations.
- Retrieve results through FastAPI.

## 21.4 Analytical acceptance tests

Use synthetic election data with known outcomes.

Example:

Historical baseline:

- District A: R+10.
- District B: R+5.
- District C: Even.
- District D: D+5.
- District E: D+10.

Apply statewide Democratic swing of +10.

Expected:

- A becomes Even.
- B becomes D+5.
- C becomes D+10.
- D becomes D+15.
- E becomes D+20.

Then supply actual results with known deviations and verify the calculations.

## 21.5 Map comparison acceptance test

Create two synthetic maps with different district boundaries.

Apply identical precinct vote totals to both maps.

Verify that:

- Vote totals are conserved.
- District winners are correctly determined.
- Seat counts are correct.
- District correspondence is calculated.
- Changes in seats are attributable to the different geographic aggregation, not different election inputs.

---

# 22. Implementation Phases

Build incrementally. Do not implement the entire specification in one pass.

## Phase 1: Core data and analytical engine

Implement:

- Map registry.
- District registry.
- Election registry.
- Contest and party models.
- Election result imports.
- Partisan baseline registry.
- Standardized partisan margins.
- Statewide swing calculations.
- Expected district margins.
- Actual district deviations.
- District classifications.

Deliverable: A working API that can analyze one map and one election.

## Phase 2: Flexible map comparison

Implement:

- Multiple map versions.
- Geographic crosswalk engine.
- Same-election map comparison.
- District correspondence.
- Seat distribution comparison.
- Competitiveness comparison.
- Geographic validation.

Deliverable: Ability to compare any two compatible maps using the same underlying election.

## Phase 3: Simulation engine

Implement:

- Uniform swing.
- Multiple swing scenarios.
- District-level winner recalculation.
- Seat response curve.
- Competitive district distribution.
- Counterfactual map comparisons.

Deliverable: Ability to model how maps behave under different political environments.

## Phase 4: Advanced analytics

Implement:

- Regional movement.
- District responsiveness.
- Outlier detection.
- Seat conversion metrics.
- Efficiency gap.
- Mean-median difference.
- Partisan bias.
- Historical comparison.

Deliverable: Comprehensive analytical reporting.

## Phase 5: Visualization and export

Implement:

- District response chart data.
- District movement map data.
- Seat response curve data.
- Map comparison data.
- GeoJSON outputs.
- CSV exports.
- Analysis configuration export.
- Reproducible reports.

Deliverable: Complete API suitable for integration with any frontend.

---

# 23. Minimum Viable Product Acceptance Criteria

The first usable release is complete when the following workflow works end-to-end:

1. Register two map versions for the same jurisdiction and chamber.
2. Import election results at precinct level.
3. Create a geographic crosswalk for each map.
4. Aggregate identical election results to both maps.
5. Import or calculate a partisan baseline.
6. Calculate historical district lean.
7. Calculate statewide political swing.
8. Calculate expected district performance.
9. Calculate actual district performance.
10. Calculate district deviations.
11. Classify districts by historical lean and actual outcome.
12. Compare the seat distribution under both maps.
13. Run D+5, D+10, D+15 and R+5 simulations.
14. Generate a seat response curve.
15. Return all results through FastAPI.
16. Reproduce the analysis using the saved configuration.

The engine must be able to accomplish this without any Georgia-specific code.

---

# 24. Important Future Enhancements

Keep the architecture open for:

- Probabilistic election forecasts.
- Monte Carlo simulations.
- Candidate-specific performance models.
- Incumbency effects.
- Turnout modeling.
- Demographic responsiveness.
- Voter registration analysis.
- Voter file integration.
- Precinct-level historical trend analysis.
- Census demographic change.
- Redistricting optimization.
- Alternative district map generation.
- Multi-party electoral systems.
- Ranked-choice voting.
- Multi-member districts.
- International electoral systems.

These should not be part of the initial implementation.

---

# 25. Final Architectural Guidance

The most important design decision is to avoid coupling the analytical engine to a particular election cycle or district map.

A map is simply a geographic definition.

An election is simply a collection of contests and vote totals.

A partisan baseline is a model of expected political behavior.

An analysis is a reproducible combination of these inputs and a set of explicit assumptions.

The engine should make it possible to change any one of those inputs independently and rerun the analysis.

In particular, preserve three separate analytical concepts:

1. **Observed electoral behavior:** What actually happened?
2. **Expected electoral behavior:** What would the historical partisan baseline and statewide swing suggest should have happened?
3. **Structural map behavior:** How would the same underlying votes translate into seats under different district maps?

Keeping these separate will make the resulting analysis much more defensible.

The ultimate goal is not simply to produce another election-results dashboard. It is to build a reusable analytical service that can explain how political preferences, geographic boundaries, and electoral outcomes interact—and how much of the resulting legislative balance can be attributed to each of those dimensions.

**Build the analytical engine first. Treat visualization as a consumer of its outputs, not as the place where the calculations happen.**

## **Two design decisions I would emphasize before implementation**

There are two things I would specifically ask the coding agent to get right.

**1. Preserve the distinction between absolute partisan lean and relative partisan lean.**

GA Explorer's 2018–24 index may represent district performance relative to the statewide environment rather than an absolute Democratic-versus-Republican margin.

These are not interchangeable.

If the index is relative partisan lean, the expected district margin should be calculated as:

\\[ Expected_i = StatewideMargin\_{current} + RelativeLean_i \\]

If it is an absolute historical district margin, then:

\\[ Expected_i = HistoricalMargin_i + StatewideSwing \\]

The baseline registry should explicitly identify which interpretation applies. It should also preserve the statewide reference margin used when constructing the baseline.

This is essential to avoid double-counting statewide movement.

**2. Make structural map comparisons a first-class feature.**

I would prioritize the ability to take one election's precinct-level results and run them through two different maps. This is arguably the strongest analytical capability in the entire project.

It lets you answer:

*"If everyone had voted exactly the same way, how different would the legislative outcome have been under the other map?"*

That is a much stronger analytical argument than comparing two elections held four years apart.

## **Suggested first implementation milestone**

I would start with Georgia, using:

- GA Explorer 2018–24 partisan index.
- December 2024 presentation's historical district classifications (particularly pages 20 and 24).
- 2022 and 2024 election results.
- Current election results.
- Existing and alternative district boundaries.

Once this works, expanding to other states should primarily be a data-ingestion exercise rather than a rewrite of the analytical engine.

The existing GA Explorer baseline and its historical classifications should remain recognizable in the new system.&#x20;

My next recommendation would be to break this specification into **five independently executable coding-agent prompts**, one per implementation phase, with explicit deliverables and acceptance tests. That will make the development much easier to manage.
