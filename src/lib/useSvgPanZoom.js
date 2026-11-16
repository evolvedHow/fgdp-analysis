import { useRef, useCallback } from 'react';

/**
 * Stub hook for SVG display (zoom/pan disabled).
 *
 * Returns a static viewBox with no interactive scaling.
 * Usage:
 *   const { viewBox, svgRef } = useSvgPanZoom(initialWidth, initialHeight);
 *   <svg viewBox={viewBox} ref={svgRef} ...>...</svg>
 */
export function useSvgPanZoom(initW, initH) {
  const viewBox = `0 0 ${initW} ${initH}`;
  const svgRef = useRef(null);

  const setupSvg = useCallback(
    (node) => {
      if (!node) return;
      svgRef.current = node;
    },
    [],
  );

  return { viewBox, svgRef: setupSvg };
}
