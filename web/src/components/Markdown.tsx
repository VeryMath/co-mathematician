import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { normalizeMath } from '../math';
import { isProjectLink } from '../projectLinks';

export function Markdown({ children, onProjectLink }: { children: string; onProjectLink?: (href: string) => void }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[[rehypeKatex, { trust: false, strict: 'ignore', maxSize: 20, maxExpand: 1000 }]]} skipHtml components={{
    a: ({ children, href }) => href && onProjectLink && isProjectLink(href) ? (
      <button type="button" className="project-file-link" onClick={() => onProjectLink(href)}>{children}</button>
    ) : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
    img: ({ alt }) => <span className="muted">[图片：{alt || '未加载'}]</span>,
  }}>{normalizeMath(children)}</ReactMarkdown></div>;
}
