import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import type { Project } from '../api';

export function ProjectResume({ project, onOpen }: { project: Project; onOpen: (path: string) => void }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  async function copyPrompt() {
    try { await navigator.clipboard.writeText(project.resume_prompt || ''); setCopied(true); setError(''); }
    catch { setError('无法自动复制，请展开下方提示并手动选取。'); }
  }
  return <details className="project-resume">
    <summary><strong>继续研究</strong><span>{project.recent_update || project.question || '查看问题、进展和下一步'}</span></summary>
    <dl>
      <div><dt>研究问题</dt><dd title={project.question}>{project.question || '尚未记录'}</dd></div>
      <div><dt>最近进展</dt><dd title={project.recent_update}>{project.recent_update || '尚未记录新的研究进展'}</dd></div>
      <div><dt>未解决问题</dt><dd title={project.blocker || project.open_question}>{project.blocker || project.open_question || '尚未记录，请在项目状态中补充'}</dd></div>
      <div><dt>下一步</dt><dd title={project.next_action}>{project.next_action || '阅读项目说明，确认下一步工作'}</dd></div>
    </dl>
    <div className="resume-actions">
      {project.latest_note && <button onClick={() => onOpen(project.latest_note!)}>打开最近笔记</button>}
      {project.resume_prompt && <button onClick={() => void copyPrompt()}>{copied ? <Check size={13}/> : <Copy size={13}/>}{copied ? '已复制接续提示' : '复制给 coding agent'}</button>}
    </div>
    {project.resume_prompt && <details className="resume-prompt"><summary>查看接续提示</summary><pre>{project.resume_prompt}</pre></details>}
    {error && <p role="status" className="error">{error}</p>}
  </details>;
}
