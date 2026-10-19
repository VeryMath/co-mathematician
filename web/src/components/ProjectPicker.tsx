import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Check, ChevronRight, FolderOpen } from 'lucide-react';
import { api, type Project, type ProjectFolders } from '../api';

export function ProjectPicker({ projects, disabled, onSelect, onOpen }: {
  projects: Project[]; disabled: boolean; onSelect: (path: string) => void;
  onOpen: (path: string) => void;
}) {
  const [folders, setFolders] = useState<ProjectFolders | null>(null);
  const [browsing, setBrowsing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [manualPath, setManualPath] = useState('');
  const [manualChanged, setManualChanged] = useState(false);
  const [filter, setFilter] = useState('');
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => { request.current?.abort(); }, []);

  async function browse(path?: string) {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBrowsing(true); setLoading(true); setError(''); setFilter(''); onSelect('');
    try {
      const result = await api<ProjectFolders>('/project-folders' + (path ? `?path=${encodeURIComponent(path)}` : ''), { signal: controller.signal });
      if (controller.signal.aborted) return;
      setFolders(result); setManualPath(result.path); setManualChanged(false); onSelect(result.projectName ? result.path : '');
    } catch (error) {
      if (!controller.signal.aborted) { setError((error as Error).message); setFolders(null); }
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }

  return <div className="project-picker">
    <p className="project-picker-intro">选择 coding agent 使用的项目文件夹，阅读已保存的研究内容。</p>
    {projects.length > 0 && <section className="recent-projects"><h3>已打开过的项目</h3>{projects.map(project => <button type="button" key={project.id} disabled={disabled || loading} onClick={() => onOpen(project.path)} title={project.path}><FolderOpen size={19}/><span><strong>{project.name}</strong><small>{project.path}</small></span><ChevronRight size={15}/></button>)}</section>}
    {!browsing ? <button className="choose-project-folder" type="button" disabled={disabled} onClick={() => void browse()}><FolderOpen size={20}/><span><strong>{projects.length ? '选择其他项目文件夹' : '选择项目文件夹'}</strong><small>浏览本机文件夹，自动识别研究项目</small></span><ChevronRight size={16}/></button> : <section className="folder-browser" aria-label="选择项目文件夹" aria-busy={loading}>
      <div className="folder-shortcuts">{folders?.shortcuts.map(shortcut => <button type="button" disabled={disabled || loading} key={shortcut.name} onClick={() => void browse(shortcut.path)}>{shortcut.name}</button>)}</div>
      <div className="folder-location"><button type="button" aria-label="上一级文件夹" title="上一级文件夹" disabled={disabled || loading || !folders?.parent} onClick={() => { if (folders?.parent) void browse(folders.parent); }}><ArrowUp size={16}/></button><span title={folders?.path}>{loading ? '正在读取文件夹…' : folders?.name || '选择文件夹'}</span><button type="button" disabled={disabled || loading} className="text-button" onClick={() => void browse()}>返回项目位置</button></div>
      {!loading && folders && <>
        {manualChanged ? <p className="folder-guidance">路径已修改，点击“前往”确认这个位置。</p> : folders.projectName ? <div className="recognized-project" role="status"><Check size={18}/><span>已找到项目 · <strong>{folders.projectName}</strong></span></div> : <p className="folder-guidance">{folders.projectError || (folders.folders.length ? '请选择下面的项目文件夹，也可以返回上一级继续查找。' : '这个文件夹里还没有研究项目，可以返回上一级继续查找。')}</p>}
        {folders.folders.length > 10 && <input className="folder-filter" aria-label="查找当前文件夹" placeholder="查找当前文件夹…" value={filter} onChange={event => setFilter(event.target.value)}/>}
        <div className="folder-list">{folders.folders.filter(folder => folder.name.toLowerCase().includes(filter.toLowerCase())).map(folder => <button type="button" key={folder.path} disabled={disabled} onClick={() => void browse(folder.path)}><FolderOpen size={16}/><span>{folder.name}</span><ChevronRight size={14}/></button>)}{!folders.folders.length && <p className="folder-empty">这里没有子文件夹。</p>}{folders.folders.length > 0 && !folders.folders.some(folder => folder.name.toLowerCase().includes(filter.toLowerCase())) && <p className="folder-empty">没有找到这个名称的文件夹。</p>}</div>
        {folders.truncated && <p className="form-help">文件夹较多，仅显示部分。可在下方直接输入要前往的位置。</p>}
      </>}
      {error && <p role="alert" className="error folder-error">{error}</p>}
      <details className="manual-project-path"><summary>手动输入路径</summary><div><input aria-label="文件夹路径" placeholder="粘贴文件夹路径" value={manualPath} disabled={disabled || loading} onChange={event => { setManualPath(event.target.value); setManualChanged(true); onSelect(''); }} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); if (manualPath.trim() && !loading && !disabled) void browse(manualPath.trim()); } }}/><button type="button" className="secondary" disabled={disabled || loading || !manualPath.trim()} onClick={() => void browse(manualPath.trim())}>前往</button></div></details>
    </section>}
    <p className="project-material-hint">新项目可以在 coding agent 中提出：“请用 Co-Math 为我新建一个研究项目。”</p>
  </div>;
}
