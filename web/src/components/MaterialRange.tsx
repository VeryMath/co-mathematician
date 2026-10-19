import { useState } from 'react';
import type { Document, MaterialSelection } from '../api';

export function MaterialRange({ document, currentPage, onApply }: {
  document: Document; currentPage: number; onApply: (selection: MaterialSelection | null) => Promise<void>;
}) {
  const pdf = /\.pdf$/i.test(document.path);
  const [start, setStart] = useState(String(document.selection?.startPage ?? document.selection?.startParagraph ?? (pdf ? currentPage : 1)));
  const [end, setEnd] = useState(String(document.selection?.endPage ?? document.selection?.endParagraph ?? (pdf ? currentPage : 1)));
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const count = pdf ? document.pageCount : document.paragraphCount;
  async function apply(reset = false) {
    const first = Number(start); const last = Number(end);
    if (!reset && (!Number.isSafeInteger(first) || !Number.isSafeInteger(last) || first < 1 || last < first || (count !== undefined && last > count))) {
      setError('请输入有效的起止范围。'); return;
    }
    if (!reset && pdf && last - first >= 40) { setError('每次最多选取 40 页。'); return; }
    setError(''); setBusy(true);
    try { await onApply(reset ? null : pdf ? { startPage: first, endPage: last } : { startParagraph: first, endParagraph: last }); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  return <details className="material-range">
    <summary>选择{pdf ? '页码' : '段落'}范围{document.selectionLabel ? ` · ${document.selectionLabel}` : ''}</summary>
    <p>{pdf ? '按 PDF 实际页序查看提取文字，每次最多 40 页。' : '按正文空行划分段落，只显示选定范围。'}{count !== undefined ? ` 共 ${count} ${pdf ? '页' : '段'}。` : ''}</p>
    <div className="range-controls"><label>从<input aria-label={pdf ? '起始页' : '起始段落'} type="number" min="1" max={count} value={start} onChange={event => setStart(event.target.value)}/></label>
      <label>至<input aria-label={pdf ? '结束页' : '结束段落'} type="number" min="1" max={count} value={end} onChange={event => setEnd(event.target.value)}/></label>
      <button disabled={busy} onClick={() => void apply()}>预览范围</button>
      {pdf && <button disabled={busy} onClick={() => { setStart(String(currentPage)); setEnd(String(currentPage)); }}>使用当前页</button>}
      {document.selection && <button disabled={busy} onClick={() => void apply(true)}>恢复默认范围</button>}
    </div>
    {error && <p role="alert" className="error">{error}</p>}
  </details>;
}
