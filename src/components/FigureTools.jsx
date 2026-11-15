import React, { useState } from 'react';
import { exportFigurePng, exportFigureSvg } from '../lib/export';

/** Turn a human label into a safe file-name fragment. */
function slug(value) {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

/**
 * Small PNG / SVG download controls attached to one chart figure.
 *
 * The buttons locate their own <figure>, so charts need no refs or export
 * plumbing beyond dropping this component inside the figure.
 */
export default function FigureTools({ name, title, subtitle, background = '#ffffff' }) {
  const [busy, setBusy] = useState(null);

  const run = async (event, fn, kind, opts) => {
    const figure = event.currentTarget.closest('figure');
    if (!figure || busy) return;
    setBusy(kind);
    try {
      await fn(figure, opts);
    } catch (err) {
      console.error('Export failed', err);
    } finally {
      setBusy(null);
    }
  };

  const filename = `fdga-xray-${slug(name)}`;

  return (
    <div className="figure-tools" role="group" aria-label="Download this chart">
      <button
        type="button"
        disabled={busy !== null}
        onClick={(e) =>
          run(e, exportFigurePng, 'png', {
            name: filename,
            title,
            subtitle,
            background,
          })
        }
        title="Download this chart as a PNG"
      >
        {busy === 'png' ? '…' : 'PNG'}
      </button>
      <button
        type="button"
        disabled={busy !== null}
        onClick={(e) => run(e, exportFigureSvg, 'svg', { name: filename, background })}
        title="Download this chart as an SVG"
      >
        SVG
      </button>
    </div>
  );
}
