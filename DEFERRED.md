# Deferred Features

## 1. County Swing Map with Geographic Positioning

**Status**: Scatter plot version complete (Section 02a). Geographic version deferred.

**What works now**:
- County-level vote shifts from one election to the next (e.g., 2020 → 2024)
- Blue arrows left (D gain), red arrows right (R gain)
- Arrow length = shift magnitude in percentage points
- Sorted by magnitude for easy reading
- Works for all election types: president, governor, US house/senate, state house/senate

**Deferred enhancement**: Full county map background

The next version should:
1. Draw Georgia county boundaries (from `counties` GeoJSON in `public/data/story.json`)
2. Position arrows at county centroids using proper geographic projection
3. Arrows emanate from the center of each county left/right
4. Maintains arrow length = shift magnitude

**Why deferred**: The coordinate transformation from GeoJSON (lon/lat, -84 to -80, 30 to 35) to SVG (0-0 origin, plotW/plotH canvas) was producing NaN coordinates due to a scaling/offset bug. Rather than debug further, the scatter plot approach was chosen for immediate usability. Geographic version is a nice-to-have visual enhancement.

**How to fix it**:
- File: `src/components/CountySwing.jsx`
- Function: `bounds` useMemo (lines ~100–104) computes GeoJSON bounds ✓
- Function: Projection functions `x(lon)`, `y(lat)` (lines ~167–169) — these produced NaN
- Fix approach:
  1. Verify `bounds.minLon/maxLon/minLat/maxLat` are numbers, not undefined
  2. Add console.log calls to the projection to debug NaN
  3. Test with a simple box/circle at known coordinates
  4. Integrate county paths rendering (currently commented out)
  5. Test on all three chambers and 5+ election pairs

**Files involved**:
- `src/components/CountySwing.jsx` — main component
- `src/App.jsx` — imports and places it (section 02a, between Statewide and SeatsVsVotes)
- Test data: `/tmp/story.json` has `counties` as a FeatureCollection with 159 Polygon features

**Acceptance criteria**:
- Arrows render at correct geographic position (visually match county outline)
- No NaN coordinates in SVG output
- Works at 375px (mobile) and 1300px (desktop) viewport widths
- Arrows still visible and readable at both scales
