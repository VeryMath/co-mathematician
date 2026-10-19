import { useLayoutEffect, useRef, useState, type PointerEvent } from 'react';

export function PanelResizer({ panel, controls }: { panel: 'sidebar'; controls: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointer: number; x: number; width: number } | null>(null);
  const [range, setRange] = useState({ value: 0, min: 0, max: 0 });
  const [dragging, setDragging] = useState(false);
  const property = `--${panel}-width`;
  const storageKey = `co-math.${panel}-width`;
  const label = '调整目录宽度';

  function geometry() {
    const handle = ref.current;
    const pane = document.getElementById(controls);
    const app = handle?.closest<HTMLElement>('.app');
    if (!handle?.parentElement || !pane || !app) return null;
    const available = handle.parentElement.clientWidth;
    const min = 180;
    const max = Math.max(min, Math.min(420, available - 328));
    return { pane, app, min, max, value: Math.round(pane.getBoundingClientRect().width) };
  }
  function sync() {
    const current = geometry();
    if (current) setRange({ value: current.value, min: current.min, max: current.max });
  }
  function change(width: number) {
    const current = geometry();
    if (!current) return;
    const value = Math.round(Math.max(current.min, Math.min(current.max, width)));
    // Resize the layout without rerendering long documents on every pointer move.
    current.app.style.setProperty(property, `${value}px`);
    sync();
  }
  function save() {
    const value = geometry()?.app.style.getPropertyValue(property);
    if (value) { try { localStorage.setItem(storageKey, String(parseFloat(value))); } catch { /* Reading and resizing still work without storage. */ } }
  }
  function reset() {
    geometry()?.app.style.removeProperty(property);
    try { localStorage.removeItem(storageKey); } catch { /* Keep the current session usable. */ }
    sync();
  }
  function finish(event?: PointerEvent<HTMLDivElement>) {
    const current = drag.current;
    if (!current || (event && event.pointerId !== current.pointer)) return;
    drag.current = null;
    document.documentElement.classList.remove('resizing-panels');
    setDragging(false); save();
    if (ref.current?.hasPointerCapture(current.pointer)) ref.current.releasePointerCapture(current.pointer);
  }

  useLayoutEffect(() => {
    const current = geometry();
    if (!current) return;
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved !== null && Number.isFinite(Number(saved)) && Number(saved) >= current.min) {
        current.app.style.setProperty(property, `${Math.min(Number(saved), 420)}px`);
      }
    } catch { /* Use the default layout when storage is unavailable. */ }
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(current.pane);
    if (ref.current?.parentElement) observer.observe(ref.current.parentElement);
    const stop = () => finish();
    window.addEventListener('blur', stop);
    return () => {
      observer.disconnect(); window.removeEventListener('blur', stop);
      if (drag.current) { drag.current = null; document.documentElement.classList.remove('resizing-panels'); }
    };
  }, [panel, controls]);

  return <div ref={ref} className={`panel-resizer ${panel}-resizer${dragging ? ' dragging' : ''}`} role="separator" tabIndex={0}
    aria-label={label} aria-orientation="vertical" aria-controls={controls} aria-valuemin={range.min} aria-valuemax={range.max} aria-valuenow={range.value} aria-valuetext={`${range.value} 像素`}
    title={`${label}，双击恢复默认；也可用左右方向键调整`}
    onPointerDown={event => {
      if (event.button !== 0 || !event.isPrimary) return;
      const current = geometry(); if (!current) return;
      event.preventDefault(); event.currentTarget.focus();
      drag.current = { pointer: event.pointerId, x: event.clientX, width: current.value };
      event.currentTarget.setPointerCapture(event.pointerId);
      document.documentElement.classList.add('resizing-panels'); setDragging(true);
    }}
    onPointerMove={event => {
      if (!drag.current || event.pointerId !== drag.current.pointer) return;
      change(drag.current.width + event.clientX - drag.current.x);
    }}
    onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish} onDoubleClick={reset}
    onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'Enter') { reset(); return; }
      const current = geometry(); if (!current) return;
      const step = event.shiftKey ? 40 : 10;
      change(event.key === 'Home' ? current.min : event.key === 'End' ? current.max : current.value + (event.key === 'ArrowRight' ? 1 : -1) * step);
      save();
    }}><span aria-hidden="true"/></div>;
}
