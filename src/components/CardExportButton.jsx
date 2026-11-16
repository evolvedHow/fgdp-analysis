import React, { useState } from 'react';
import { exportCardPng } from '../lib/export';

/**
 * Button to export a card as PNG.
 * Locates the nearest .story-card parent.
 */
export default function CardExportButton({ filename }) {
  const [busy, setBusy] = useState(false);

  const handleClick = async (e) => {
    if (busy) return;
    
    const card = e.currentTarget.closest('.story-card');
    if (!card) {
      console.error('No card found for export');
      return;
    }

    setBusy(true);
    try {
      await exportCardPng(card, filename);
    } catch (err) {
      console.error('Card export failed', err);
      alert('Failed to export card. Try a desktop browser.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      disabled={busy}
      onClick={handleClick}
      className="card-export-btn"
      title="Export this card as PNG"
      aria-label={`Export ${filename} as PNG`}
    >
      {busy ? '…' : '📥'}
    </button>
  );
}
