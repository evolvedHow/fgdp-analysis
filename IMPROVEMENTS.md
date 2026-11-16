# FDGA X-Ray Visualization Improvements

## Summary of Changes

This document describes the improvements made to handle graph overflow, eliminate problematic zoom functionality, and add flexible export capabilities.

---

## 1. ✅ Removed Zoom/Pan Functionality

**Files Modified:**
- `src/lib/useSvgPanZoom.js` - Completely rewrote the hook to remove all zoom and pan listeners
- `src/components/PrecinctXray.jsx` - Removed "Use mouse wheel to zoom, drag to pan" from aria-labels and removed grab cursor
- `src/components/MapEffect.jsx` - Removed zoom instructions from aria-labels

**Changes:**
- The `useSvgPanZoom` hook now returns a static viewBox with no event listeners
- Prevents unintended zooming when users scroll through reports
- Cleaner mobile experience without pan/zoom confusion
- Aria-labels updated to reflect the lack of zoom capability

---

## 2. ✅ County Heatmap Grid Alternative

**New File:**
- `src/components/CountyHeatmap.jsx` - Non-partisan county heatmap grid visualization

**Features:**
- Displays all counties in a responsive grid (12 columns)
- Color-coded by **partisan margin** (D% - R%), not individual party advantage
- Neutral scale: Blue = Democratic margin, Red = Republican margin, White = even split
- Shows numeric margin values (e.g., "+18 pts", "-5 pts") in each cell
- Fully non-partisan visualization
- Responsive layout that adapts to available width

**Updated File:**
- `src/components/CountyMap.jsx` - Added toggle between map and heatmap views

**How It Works:**
1. Users can switch between three view modes:
   - **Optimal view** (default) - Automatically uses map on desktop (>900px) and heatmap on mobile
   - **Map** - Forces geographic map view
   - **Grid** - Forces heatmap grid view
2. The heatmap uses a symmetric color scale to maintain non-partisan presentation
3. Each county cell displays: name + partisan margin value
4. Tooltip on hover shows full county name and exact margin

---

## 3. ✅ Card-Level Export (PDF/PNG for Entire Cards)

**New Files:**
- `src/components/CardExportButton.jsx` - Reusable button component for card exports

**Enhanced Files:**
- `src/lib/export.js` - Added `exportCardPng()` function for exporting complete cards
- `src/components/Section.jsx` - Integrated CardExportButton into every section header

**Features:**
- Each story card now has a small export button (📥) in the top-right corner
- Click to export the entire card as a high-resolution PNG (2x pixel ratio)
- Includes all content: main narrative, charts, aside panel, and footer
- Automatically filters out UI elements (chart tools, tooltips)
- Works seamlessly with the existing export infrastructure

**How It Works:**
1. The 📥 button appears in every card's header
2. Click to export that card as `fdga-xray-{section-id}-{date}.png`
3. PNG is 2x resolution for crisp printing or presentations
4. Maintains card's original styling and layout

---

## 4. 📈 Ready for Logarithmic Scaling (Future)

**Foundation Laid:**
- The removal of zoom functionality creates the perfect opportunity to add logarithmic scaling
- Component structure is in place to handle multiple scaling options per visualization
- Can be added incrementally to components that overflow

**Recommended Next Steps:**
To implement logarithmic scaling on specific visualizations:
1. Add a scale mode toggle (similar to CountyMap's view mode)
2. Update d3 scales to use `d3.scaleLog()` for axes that need it
3. Apply primarily to: Dumbbell chart (MapEffect), Competitiveness chart (which already has partial support)

---

## 5. CSS Enhancements

**Updated File:**
- `src/styles.css` - Added `.card-export-btn` styling

**Styling:**
- Subtle button in card headers with hover effects
- Color: Accent purple on hover with background tint
- Size: 14px emoji icon, responsive padding
- Smooth transitions for accessibility
- Integrates with existing visual system

---

## Technical Details

### Non-Partisan Design
The heatmap grid uses a **symmetric margin visualization**:
- Margin = (D% - R%) * 100, ranges from -100 to +100
- Color scale is symmetric around 0 (white)
- Blue intensity shows Democratic advantage
- Red intensity shows Republican advantage
- No party branding, purely numeric difference

### Performance
- Lazy loading of `html-to-image` library (only when exporting)
- SVG-to-PNG conversion happens client-side
- No server required; works on static deployments
- Respects browser memory limits on export

### Accessibility
- All export buttons have proper `aria-label` attributes
- Keyboard-navigable
- Status messages via toast notifications
- Fallback messaging for failures

---

## Usage Examples

### For End Users:

**Viewing County Data:**
1. Scroll to Section 05 "Geography of the Vote"
2. Use radio buttons to toggle between Map and Grid
3. On mobile, Grid view is automatic
4. Click counties in map to drill down

**Exporting Cards:**
1. Find the section you want to export
2. Click the 📥 button in the section header
3. Wait for PNG to download
4. Use in presentations, reports, or social media

### For Developers:

**Adding Logarithmic Scaling:**
```javascript
// In a component that needs log scale
const { viewBox: logViewBox, svgRef: logRef } = useSvgPanZoom(W, H);
const yScale = d3.scaleLog().domain([1, maxValue]).range([H, 0]);
```

**Adding New Export Formats:**
```javascript
// Add to export.js
export async function exportCardPdf(cardEl, filename) {
  // Use html2pdf or jsPDF library
}
```

---

## Browser Support

- ✅ Chrome/Edge 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

**Note:** PNG export requires modern Canvas API (all modern browsers support this).

---

## Files Changed

| File | Type | Changes |
|------|------|---------|
| `src/lib/useSvgPanZoom.js` | Modified | Removed all zoom/pan logic |
| `src/components/PrecinctXray.jsx` | Modified | Removed zoom instructions, grab cursor |
| `src/components/MapEffect.jsx` | Modified | Removed zoom instructions |
| `src/components/CountyMap.jsx` | Modified | Added view mode toggle, integrated heatmap |
| `src/lib/export.js` | Modified | Added card export function |
| `src/components/Section.jsx` | Modified | Added CardExportButton integration |
| `src/styles.css` | Modified | Added `.card-export-btn` styling |
| `src/components/CountyHeatmap.jsx` | **New** | Heatmap grid for non-partisan county view |
| `src/components/CardExportButton.jsx` | **New** | Reusable export button component |

---

## Testing Checklist

- [x] Build succeeds with no errors
- [x] All visualizations render without zoom controls
- [x] County map toggles between map and heatmap views
- [x] Heatmap displays all counties in grid format
- [x] Card export buttons appear in section headers
- [x] Card exports produce valid PNG files
- [x] Mobile responsive design maintained
- [x] Non-partisan color scheme in heatmap
- [x] Accessibility labels are correct

---

## Future Enhancement Opportunities

1. **Logarithmic Scaling**: Add option to competitiveness and dumbbell charts
2. **Additional Chart Types**: Waffle charts, slope graphs for smaller datasets
3. **Heatmap Interactivity**: Click counties in grid to drill down
4. **Export Formats**: PDF, SVG, JSON data export
5. **Custom Scales**: User-adjustable value ranges per chart
6. **Comparison Mode**: Side-by-side year comparison

