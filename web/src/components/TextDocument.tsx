import { useState } from 'react';
import type { Document } from '../api';
import { Markdown } from './Markdown';
import { MathText } from './MathText';

export function TextDocument({ document, onProjectLink }: { document: Document; onProjectLink: (href: string) => void }) {
  const [source, setSource] = useState(false);
  const markdown = document.format === 'markdown' || /\.md$/i.test(document.path);
  const readableText = markdown || /\.(txt|tex|docx|pdf)$/i.test(document.path);
  if (!readableText) return <pre className="source-document">{document.content}</pre>;
  return <>
    <div className="document-view-tabs" role="group" aria-label="文档显示方式"><button aria-pressed={!source} onClick={() => setSource(false)}>阅读</button><button aria-pressed={source} onClick={() => setSource(true)}>源文</button></div>
    {source ? <pre className="source-document text-source">{document.content}</pre> :
      markdown ? <Markdown onProjectLink={onProjectLink}>{document.content}</Markdown> :
        <MathText latex={/\.tex$/i.test(document.path)}>{document.content || '暂无可显示的正文。'}</MathText>}
  </>;
}
