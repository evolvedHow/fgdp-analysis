/**
 * Client-side export helpers: PNG / SVG for a single figure and PNG / PDF for
 * the whole report. Everything runs in the browser — the published site has no
 * server, so no export may depend on one.
 *
 * Figures are rasterised from their inline SVG (fast, exact, no screenshot
 * library) with a caption band drawn on top. The full report is captured with
 * `html-to-image`, which is loaded lazily so the initial bundle stays small.
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

/** Inline stylesheet applied to a serialised SVG — external CSS is lost. */
const SVG_STYLE = `
  text { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, Arial, sans-serif; }
  .axis-label { font-size: 9.5px; fill: #726d89; }
  .axis-label.is-current { fill: #1c1a2b; font-weight: 700; }
  .bar-value { font-size: 10px; fill: #4c4863; font-weight: 700; }
  .gridline { stroke: #eeecf4; stroke-width: 1; }
  .zero-line { stroke: #bdb7cf; stroke-width: 1; stroke-dasharray: 3 3; }
  .scale-break { stroke: #bdb7cf; stroke-width: 1; stroke-dasharray: 4 4; }
  .axis-line { stroke: #d7d3e3; stroke-width: 1; }
  .year-rule { stroke: #6440a4; stroke-width: 1; stroke-dasharray: 2 4; opacity: 0.55; }
  .year-flag { font-size: 10px; font-weight: 700; fill: #6440a4; letter-spacing: 0.04em; }
  .bench-label { font-size: 10.5px; font-weight: 600; fill: #4c4863; }
  .bench-label.is-outside { fill: #7d3169; font-weight: 700; }
  .bench-value { font-size: 9.5px; fill: #726d89; }
  .bench-value.is-strong { fill: #7d3169; font-weight: 700; font-size: 10px; }
  .grade-chip-text { font-size: 9.5px; font-weight: 700; fill: #ffffff; }
  .county { stroke: #ffffff; stroke-width: 0.6; }
  .county.is-selected { stroke: #1c1a2b; stroke-width: 2; }
  .county-outline { fill: #f5f3fa; stroke: #e2dfeb; stroke-width: 0.7; }
  .county-outline.is-strong { fill: #efecf7; stroke: #4c4863; stroke-width: 1.2; }
  .precinct-dot { stroke: #ffffff; stroke-width: 0.5; }
  .precinct-dot.is-selected { stroke: #1c1a2b; stroke-width: 2.2; }
  .dot { fill-opacity: 1; }
`;

const FONT = "'Inter', 'Segoe UI', system-ui, -apple-system, Arial, sans-serif";

/** Trigger a browser download for a Blob. */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Give the browser a tick to start the download before revoking.
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/** Load an image element from a URL, rejecting if it cannot decode. */
function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Could not rasterise the chart'));
    img.src = src;
  });
}

/** Clone an SVG with explicit pixel size, background and inline styles. */
function prepareSvg(svg, background) {
  const clone = svg.cloneNode(true);
  const vb = svg.viewBox && svg.viewBox.baseVal;
  const width = Math.round((vb && vb.width) || svg.clientWidth || 640);
  const height = Math.round((vb && vb.height) || svg.clientHeight || 360);

  clone.setAttribute('xmlns', SVG_NS);
  clone.setAttribute('width', String(width));
  clone.setAttribute('height', String(height));

  const style = document.createElementNS(SVG_NS, 'style');
  style.textContent = SVG_STYLE;
  clone.insertBefore(style, clone.firstChild);

  const bg = document.createElementNS(SVG_NS, 'rect');
  bg.setAttribute('x', '0');
  bg.setAttribute('y', '0');
  bg.setAttribute('width', String(width));
  bg.setAttribute('height', String(height));
  bg.setAttribute('fill', background);
  clone.insertBefore(bg, style.nextSibling);

  return { clone, width, height };
}

/** Serialise an SVG node to a standalone string. */
function svgToString(svg, background) {
  const { clone } = prepareSvg(svg, background);
  return new XMLSerializer().serializeToString(clone);
}

/** Trim a string with an ellipsis so it fits a pixel width. */
function fitText(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let out = text;
  while (out.length > 1 && ctx.measureText(`${out}…`).width > maxWidth) {
    out = out.slice(0, -1);
  }
  return `${out}…`;
}

/** Rasterise an inline SVG to a PNG Blob with a caption band on top. */
async function svgToPngBlob(svg, { title, subtitle, background = '#ffffff', scale = 2 }) {
  const xml = svgToString(svg, background);
  const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }));
  let img;
  try {
    img = await loadImage(url);
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  const cssWidth = img.naturalWidth || 640;
  const cssHeight = img.naturalHeight || 360;
  const band = title || subtitle ? 58 : 0;

  const canvas = document.createElement('canvas');
  canvas.width = Math.round(cssWidth * scale);
  canvas.height = Math.round((cssHeight + band) * scale);
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, band * scale, cssWidth * scale, cssHeight * scale);

  if (band) {
    const pad = 18;
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = '#1c1a2b';
    ctx.font = `800 ${13 * scale}px ${FONT}`;
    ctx.fillText(fitText(ctx, title || '', (cssWidth - pad * 2) * scale), pad * scale, 24 * scale);
    ctx.fillStyle = '#726d89';
    ctx.font = `500 ${10.5 * scale}px ${FONT}`;
    ctx.fillText(
      fitText(ctx, subtitle || '', (cssWidth - pad * 2) * scale),
      pad * scale,
      42 * scale,
    );
    ctx.textAlign = 'right';
    ctx.fillStyle = '#6440a4';
    ctx.font = `700 ${10 * scale}px ${FONT}`;
    ctx.fillText('FDGA X-Ray', (cssWidth - pad) * scale, 24 * scale);
  }

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('PNG encoding failed');
  return blob;
}

/**
 * Export one figure as a high-resolution PNG.
 * @param {HTMLElement} figureEl the <figure> containing an <svg>
 * @param {{name:string,title:string,subtitle?:string,background?:string}} opts
 */
export async function exportFigurePng(figureEl, { name, title, subtitle, background = '#ffffff' }) {
  const svg = figureEl?.querySelector('svg');
  if (!svg) throw new Error('No chart found in this figure');
  const blob = await svgToPngBlob(svg, { title, subtitle, background });
  downloadBlob(blob, `${name}.png`);
}

/** Export one figure as a standalone, self-styled SVG file. */
export function exportFigureSvg(figureEl, { name, background = '#ffffff' }) {
  const svg = figureEl?.querySelector('svg');
  if (!svg) throw new Error('No chart found in this figure');
  const xml = svgToString(svg, background);
  const doc = `<?xml version="1.0" encoding="UTF-8"?>\n${xml}`;
  downloadBlob(new Blob([doc], { type: 'image/svg+xml;charset=utf-8' }), `${name}.svg`);
}

/** Human-friendly timestamp for file names. */
function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

/**
 * Capture the whole story as one tall PNG: every section card is rendered,
 * then stitched vertically on a lavender canvas.
 * @param {{filename?:string, background?:string}} [opts]
 * @returns {Promise<number>} number of cards captured
 */
export async function exportReportPng({ filename, background = '#e8e6ef' } = {}) {
  const { toPng } = await import('html-to-image');
  const cards = Array.from(document.querySelectorAll('.story-card'));
  if (!cards.length) throw new Error('No story sections found');

  document.body.classList.add('is-exporting');
  try {
    const rects = cards.map((c) => c.getBoundingClientRect());
    const cssWidth = Math.max(...rects.map((r) => r.width));
    const cssHeight =
      rects.reduce((sum, r) => sum + r.height, 0) + 26 * (cards.length - 1);

    // Keep the stitched canvas inside browser limits (Chrome ~268 MP, but
    // stay well under to avoid multi-hundred-MB images on phones).
    const MAX_PIXELS = 36e6;
    let scale = 1.5;
    if (cssWidth * cssHeight * scale * scale > MAX_PIXELS) {
      scale = Math.max(0.75, Math.sqrt(MAX_PIXELS / (cssWidth * cssHeight)));
    }
    if (cssHeight * scale > 28000) scale = 28000 / cssHeight;

    const shots = [];
    for (const card of cards) {
      const dataUrl = await toPng(card, {
        pixelRatio: scale,
        backgroundColor: '#ffffff',
        cacheBust: true,
        filter: (node) =>
          !(
            node instanceof Element &&
            (node.classList?.contains('figure-tools') ||
              node.classList?.contains('card-actions') ||
              node.classList?.contains('map-tooltip') ||
              node.classList?.contains('chart-tooltip'))
          ),
      });
      shots.push(dataUrl);
    }

    const images = await Promise.all(shots.map(loadImage));
    const gap = Math.round(26 * scale);
    const width = Math.max(...images.map((i) => i.naturalWidth));
    const height =
      images.reduce((sum, i) => sum + i.naturalHeight, 0) + gap * (images.length - 1);

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, width, height);

    let y = 0;
    for (const img of images) {
      ctx.drawImage(img, Math.round((width - img.naturalWidth) / 2), y);
      y += img.naturalHeight + gap;
    }

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('PNG encoding failed');
    downloadBlob(blob, filename || `fdga-xray-report-${stamp()}.png`);
    return cards.length;
  } finally {
    document.body.classList.remove('is-exporting');
  }
}

/**
 * Export a single card (section) as PNG.
 * @param {HTMLElement} cardEl the <section class="story-card">
 * @param {string} filename output filename without extension
 */
export async function exportCardPng(cardEl, filename) {
  const { toPng } = await import('html-to-image');
  
  if (!cardEl || !(cardEl instanceof Element)) {
    throw new Error('No card element found');
  }

  document.body.classList.add('is-exporting');
  try {
    const dataUrl = await toPng(cardEl, {
      pixelRatio: 2,
      backgroundColor: '#ffffff',
      cacheBust: true,
      filter: (node) =>
        !(
          node instanceof Element &&
          (node.classList?.contains('figure-tools') ||
            node.classList?.contains('card-actions') ||
            node.classList?.contains('map-tooltip') ||
            node.classList?.contains('chart-tooltip'))
        ),
    });
    
    const img = await loadImage(dataUrl);
    const blob = await new Promise((resolve) => {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);
      canvas.toBlob(resolve, 'image/png');
    });
    
    if (!blob) throw new Error('PNG encoding failed');
    downloadBlob(blob, `${filename}.png`);
  } finally {
    document.body.classList.remove('is-exporting');
  }
}

/** Open the browser print dialog; the print stylesheet produces the PDF. */
export function printReport() {
  window.print();
}
