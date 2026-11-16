# Quick Start: New Features

## What Changed

### 1. No More Zoom Interference
**Before:** Scrolling through the report would trigger unwanted zooming on SVG charts
**After:** Smooth scrolling throughout, charts display at full resolution without zoom controls

---

## 2. County View Toggle (Section 05)

### Three View Modes Available:

#### 🗺️ Map View (Default on Desktop)
- Geographic choropleth of counties
- Click counties to drill into precincts
- Responsive, maintains spatial relationships

#### 📊 Grid View (Default on Mobile, <900px width)
- All counties in a 12-column grid
- Color-coded by **partisan margin** (balanced, non-partisan)
  - 🔵 Blue = Democratic margin advantage
  - ⚪ White = Even split (50-50)
  - 🔴 Red = Republican margin advantage
- Each cell shows: County name + margin value (e.g., "-5 pts")
- Perfect for comprehensive data review
- No geographic bias in visualization

#### ✨ Optimal View (Auto-switches based on screen size)
- Recommended default
- Automatically picks best format for your device

### How to Use:
```
Section 05: "Geography of the Vote"
     ↓
Look for view toggle buttons:
  ○ Optimal view  ○ Map  ○ Grid
     ↓
Click your preferred view
```

---

## 3. Card Export (All Sections)

### New 📥 Button in Every Card Header

Appears in the top-right corner of each section.

**What It Exports:**
- ✅ All charts and visualizations
- ✅ Main narrative text
- ✅ Aside panel (rankings, statistics)
- ✅ Footer (methodology notes)
- ✅ High resolution (2x pixel ratio)

**What It Excludes:**
- ❌ Chart download buttons
- ❌ Tooltips
- ❌ Interactive elements

### Example Export Workflow:

```
Section 01: "The Swing"
     ↓
See 📥 button (top-right)
     ↓
Click it
     ↓
PNG downloads: fdga-xray-swing-2026-11-16.png
     ↓
Use in PowerPoint, Twitter, Reports, etc.
```

---

## 4. Non-Partisan Presentation

### Key Design Principle:
**All new visualizations are balanced and non-partisan**

**Example: County Heatmap**
- Shows partisan **margin** (the difference), not individual party percentages
- Symmetric color scale (D ← Center → R)
- No visual bias toward any party
- Numbers tell the story, colors show magnitude

```
Margin = Democratic% - Republican%

Examples:
  +20 pts = 60% D vs 40% R (Blue)
  -10 pts = 45% D vs 55% R (Red)  
   0 pts = 50% D vs 50% R (White)
```

---

## Mobile Experience

### Automatic Adaptation:
- **Wide screens (>900px):** Map view by default
- **Mobile (<900px):** Grid view by default
- **User override:** Always available via radio buttons
- **No pinch-zoom confusion:** Zoom controls removed entirely

### Mobile Card Exports:
- Works on all devices
- Respects memory constraints
- Downloads scale appropriately for smaller screens

---

## Common Questions

### Q: Where's the zoom feature?
**A:** Removed to prevent scroll interference and simplify mobile experience. All content is designed to fit standard viewport widths.

### Q: Can I still drill into counties?
**A:** Yes! On the **Map view**, click any county to open its precincts. The grid view is read-only for comprehensive scanning.

### Q: What if the map looks crowded?
**A:** Switch to **Grid view** for a clean, organized table of all counties. The margin values are clearly labeled.

### Q: Can I export just one chart?
**A:** Yes! Each chart has its own **PNG/SVG** buttons (chart-level export). The 📥 button exports the **entire card** with narrative.

### Q: What format are the card exports?
**A:** PNG only (high-resolution, works everywhere). Full-report PDF export is still available via Print dialog.

### Q: Can I edit the exported images?
**A:** PNG exports are rasterized images, not editable. Use SVG export for individual charts if editing is needed.

---

## Keyboard Navigation

### Export Button Shortcut:
1. Tab to any 📥 button
2. Press Enter to export
3. PNG downloads (varies by browser)

### View Mode Toggle:
1. Tab to radio buttons in county section
2. Use Arrow keys to change selection
3. View updates immediately

---

## Troubleshooting

### Export Button Not Appearing
- Refresh the page
- Check browser console for errors
- Ensure JavaScript is enabled

### PNG Export Fails
- Try a desktop browser (mobile sometimes struggles with large files)
- Use "Report PDF" via Print dialog as fallback
- Clear browser cache and retry

### Heatmap Colors Not Showing
- Check that you're not in dark mode (may need color adjustments)
- Ensure JavaScript is enabled
- Try refreshing the page

---

## Best Practices

### For Reports:
1. Use **Map view** to show geographic patterns
2. Use **Card exports** to create a deck of findings
3. Include **margin values** when discussing county data

### For Presentations:
1. Export entire cards for consistent branding
2. Use grid view to show comprehensive county coverage
3. Reference specific margin values, not just colors

### For Data Analysis:
1. Grid view lets you scan all 159 counties at once
2. Hover tooltips show exact values
3. Numbers are always precise; colors aid visual scanning

---

## Browser Compatibility

✅ Works great in:
- Chrome/Edge (latest 2 versions)
- Firefox (latest 2 versions)
- Safari (latest 2 versions)
- Mobile Safari & Chrome

⚠️ May have issues in:
- Internet Explorer (not supported)
- Very old mobile browsers
- Devices with <512MB RAM

---

## Feedback & Issues

If you encounter:
- **Export failures:** Check browser console, try different device
- **Layout issues:** Report screen resolution and browser
- **Color display issues:** May be browser-specific rendering
- **Performance problems:** Close other browser tabs, check device RAM

