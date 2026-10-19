import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type RenderTask } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfPreview({ url, initialPage = 1, onPageChange }: { url: string; initialPage?: number; onPageChange?: (page: number) => void }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1); const [pageInput, setPageInput] = useState('1');
  const [width, setWidth] = useState(0); const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const container = useRef<HTMLDivElement>(null); const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    setPdf(null); setPage(initialPage); setPageInput(String(initialPage)); setError(''); setLoading(true);
    let disposed = false;
    const task = getDocument({ url, useWasm: false, useSystemFonts: true, disableRange: true, disableStream: true,
      cMapUrl: `${window.location.origin}/pdf-assets/cmaps/`, cMapPacked: true,
      standardFontDataUrl: `${window.location.origin}/pdf-assets/standard_fonts/`,
    });
    void task.promise.then(document => {
      if (disposed) return;
      const next = Math.min(document.numPages, Math.max(1, initialPage));
      setPage(next); setPageInput(String(next)); setPdf(document);
      if (next !== initialPage) onPageChange?.(next);
    }).catch(() => { if (!disposed) { setError('暂时无法显示原始页面，可以下载原文件查看。'); setLoading(false); } });
    return () => { disposed = true; void task.destroy().catch(() => {}); };
  }, [url]);

  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(1, entries[0].contentRect.width)));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!pdf || !canvas.current || !width) return;
    let disposed = false; let rendering: RenderTask | undefined;
    setLoading(true); setError('');
    void pdf.getPage(page).then(async original => {
      if (disposed || !canvas.current) return;
      const base = original.getViewport({ scale: 1 });
      const viewport = original.getViewport({ scale: width / base.width });
      const density = Math.min(window.devicePixelRatio || 1, 2);
      const surface = document.createElement('canvas');
      surface.width = Math.ceil(viewport.width * density); surface.height = Math.ceil(viewport.height * density);
      rendering = original.render({ canvas: surface, viewport, transform: [density, 0, 0, density, 0, 0] });
      await rendering.promise;
      if (!disposed && canvas.current) {
        canvas.current.width = surface.width; canvas.current.height = surface.height;
        canvas.current.getContext('2d')?.drawImage(surface, 0, 0);
        setLoading(false);
      }
    }).catch(reason => { if (!disposed && reason?.name !== 'RenderingCancelledException') { setError('这一页无法显示，请尝试其他页或下载原文件。'); setLoading(false); } });
    return () => { disposed = true; rendering?.cancel(); };
  }, [pdf, page, width]);

  function navigate(number: number) {
    if (!pdf) return;
    const next = Math.min(pdf.numPages, Math.max(1, Number.isFinite(number) ? Math.trunc(number) : page));
    setPage(next); setPageInput(String(next));
    onPageChange?.(next);
  }
  return <div className="pdf-preview">
    <div className="pdf-page-controls"><button aria-label="上一页" disabled={!pdf || page <= 1} onClick={() => navigate(page - 1)}><ChevronLeft size={17}/></button>
      <span>第 <input aria-label="PDF 页码" inputMode="numeric" value={pageInput} disabled={!pdf} onChange={event => setPageInput(event.target.value)} onBlur={() => navigate(Number(pageInput))} onKeyDown={event => { if (event.key === 'Enter') navigate(Number(pageInput)); }}/> 页 / {pdf?.numPages ?? '…'}</span>
      <button aria-label="下一页" disabled={!pdf || page >= pdf.numPages} onClick={() => navigate(page + 1)}><ChevronRight size={17}/></button>
      {loading && <small role="status">正在显示…</small>}
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="pdf-page-surface" ref={container}><canvas ref={canvas} aria-label={`PDF 原文第 ${page} 页`} style={{ visibility: pdf && !error ? 'visible' : 'hidden' }}/></div>
  </div>;
}
