
## 2026-11-14: County Swing Scatter Plot (Section 02a)

**Added**: Interactive county-level vote shift visualization.

- **What**: Blue arrows (left) for D gains, red arrows (right) for R gains, length = shift magnitude
- **Data**: Compares consecutive elections (e.g., 2020 pres → 2024 pres, 2018 gov → 2022 gov)
- **Placement**: Section 02a, between Statewide (01) and Votes vs Seats (02)
- **Status**: ✓ Scatter plot working. Deferred: geographic version with county boundaries.

**Deferred Work** (documented in `DEFERRED.md`):
- Geographic map background: position arrows at county centroids on GA map
- Reason deferred: coordinate transform (GeoJSON lon/lat → SVG) had NaN bug
- Future: Add console debugging, test projection math, integrate county path rendering

**Files changed**:
- `src/components/CountySwing.jsx` (new)
- `src/App.jsx` (added import, nav entry, render call)
- `DEFERRED.md` (created, includes fix strategy)

**Live**: Deployed to evolvedhow.github.io/fdga-xray as section 02a


## 2026-11-14 EOD: Pan/Zoom Implementation & Visual Regression

**Deployed today**:
- ✓ Sticky navigation breadcrumbs (stays at top while scrolling)
- ✓ Pan/zoom hook created (`src/lib/useSvgPanZoom.js`)
- ✓ Pan/zoom integrated into Section #3 (dumbbell) and Section #7 (precinct map)
- ✓ Improved displacement chart labels (staggered, connector lines)

**Issue identified**:
- Pan/zoom causes SVG to overflow horizontally when zoomed in
- Only the diagram breaks layout; surrounding content stays fixed
- Creates bad UX: users zoom in but then can't see full zoomed area without horizontal scrolling
- **Root cause**: SVG viewBox transforms but container width is fixed (640px, 700px)

**Recommendation for tomorrow**:
Instead of pan/zoom directly on SVGs, consider:
1. **Bounded viewport**: Constrain pan to never overflow container edges
2. **Collapsible detail panel**: Click to expand chart to full-width overlay, then pan/zoom
3. **Separate detail view**: Link from chart to a dedicated zoomed view (e.g., modal or separate section)
4. **SVG clipping**: Use CSS `overflow: hidden` on SVG container to hide overflow (loses detail access)
5. **Responsive containers**: Let charts grow to viewport width on zoom (complex with grid layout)

**Files affected**:
- `src/lib/useSvgPanZoom.js` — hook is solid, issue is integration
- `src/components/MapEffect.jsx` — section #3 with pan/zoom
- `src/components/PrecinctXray.jsx` — section #7 with pan/zoom

**Live at**:
- https://evolvedhow.github.io/fdga-xray/ (deployed, pan/zoom live but visually broken)

**Next session**:
1. Revert pan/zoom integration (keep hook for later)
2. Rebuild without SVG transforms, or
3. Implement bounded viewport + overflow clipping
4. Test UX improvement before re-deploying

**Code status**: All pushed to main (`fgdp` and `fdga-xray` synced)
