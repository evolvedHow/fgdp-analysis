import { useState, useRef, useCallback } from 'react';

/**
 * Custom hook for pan/zoom on SVG elements.
 *
 * Allows readers to zoom (mouse wheel) and pan (drag) within an SVG chart.
 * Zoom is bounded to [minZoom, maxZoom]; pan is bounded to the viewBox bounds.
 *
 * Usage:
 *   const { viewBox, svgRef } = useSvgPanZoom(initialWidth, initialHeight, minZoom, maxZoom);
 *   <svg viewBox={viewBox} ref={svgRef} ...>...</svg>
 */
export function useSvgPanZoom(initW, initH, minZoom = 1, maxZoom = 10) {
  const [viewBox, setViewBox] = useState(`0 0 ${initW} ${initH}`);
  const svgRef = useRef(null);
  const stateRef = useRef({
    x: 0,
    y: 0,
    scale: 1,
    isDragging: false,
    dragStart: null,
  });

  const updateViewBox = useCallback(() => {
    const { x, y, scale } = stateRef.current;
    const w = initW / scale;
    const h = initH / scale;
    setViewBox(`${x} ${y} ${w} ${h}`);
  }, [initW, initH]);

  const clampPan = useCallback((x, y, scale) => {
    const w = initW / scale;
    const h = initH / scale;
    const clampedX = Math.max(0, Math.min(x, initW - w));
    const clampedY = Math.max(0, Math.min(y, initH - h));
    return [clampedX, clampedY];
  }, [initW, initH]);

  const handleWheel = useCallback(
    (e) => {
      if (!svgRef.current) return;
      e.preventDefault();

      const rect = svgRef.current.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // Convert screen coords to viewBox coords
      const [vx, vy, vw, vh] = viewBox.split(' ').map(Number);
      const viewX = vx + (mouseX / rect.width) * vw;
      const viewY = vy + (mouseY / rect.height) * vh;

      const delta = e.deltaY > 0 ? 1.1 : 0.9;
      const newScale = Math.max(minZoom, Math.min(maxZoom, stateRef.current.scale * delta));
      const scaleDiff = newScale / stateRef.current.scale;

      // Keep the point under the cursor constant
      const newX = viewX - ((viewX - vx) / scaleDiff);
      const newY = viewY - ((viewY - vy) / scaleDiff);
      const [clampedX, clampedY] = clampPan(newX, newY, newScale);

      stateRef.current.scale = newScale;
      stateRef.current.x = clampedX;
      stateRef.current.y = clampedY;
      updateViewBox();
    },
    [viewBox, clampPan, updateViewBox, minZoom, maxZoom],
  );

  const handleMouseDown = useCallback((e) => {
    stateRef.current.isDragging = true;
    stateRef.current.dragStart = { x: e.clientX, y: e.clientY };
  }, []);

  const handleMouseMove = useCallback(
    (e) => {
      if (!stateRef.current.isDragging || !stateRef.current.dragStart) return;

      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;

      const [vx, vy, vw, vh] = viewBox.split(' ').map(Number);
      const dx = ((e.clientX - stateRef.current.dragStart.x) / rect.width) * vw * -1;
      const dy = ((e.clientY - stateRef.current.dragStart.y) / rect.height) * vh * -1;

      const [clampedX, clampedY] = clampPan(vx + dx, vy + dy, stateRef.current.scale);
      stateRef.current.x = clampedX;
      stateRef.current.y = clampedY;
      stateRef.current.dragStart = { x: e.clientX, y: e.clientY };

      updateViewBox();
    },
    [viewBox, clampPan, updateViewBox],
  );

  const handleMouseUp = useCallback(() => {
    stateRef.current.isDragging = false;
    stateRef.current.dragStart = null;
  }, []);

  // Attach global listeners for mouse move/up (to work even when mouse leaves SVG)
  const attachListeners = useCallback(() => {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const setupSvg = useCallback(
    (node) => {
      if (!node) return;
      svgRef.current = node;
      node.addEventListener('wheel', handleWheel, { passive: false });
      node.addEventListener('mousedown', handleMouseDown);
      attachListeners();
    },
    [handleWheel, handleMouseDown, attachListeners],
  );

  return { viewBox, svgRef: setupSvg };
}
