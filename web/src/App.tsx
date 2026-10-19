import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, BookOpen, Check, ChevronRight, Copy, Download, FileText, FolderOpen, History, PanelLeftClose, RefreshCw, X } from 'lucide-react';
import { api, type Document, type MaterialSelection, type Project, type ProjectFile } from './api';
import { TextDocument } from './components/TextDocument';
import { Modal, ProjectDialog } from './components/Dialogs';
import { GoalsView } from './components/GoalsView';
import { PanelResizer } from './components/PanelResizer';
import { FileBrowser } from './components/FileBrowser';
import { MaterialRange } from './components/MaterialRange';
import { ConversationHistory } from './components/ConversationHistory';
import verymathLogo from './assets/verymath-logo.png?inline';

const PdfPreview = lazy(() => import('./components/PdfPreview'));

function savedProject() {
  try { return localStorage.getItem('co-math-project') || ''; } catch { return ''; }
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(savedProject);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [fileRevision, setFileRevision] = useState(0);
  const [document, setDocument] = useState<Document | null>(null);
  const [selectedFile, setSelectedFile] = useState<{ path: string; selection: MaterialSelection | null } | null>(null);
  const [openingFile, setOpeningFile] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfView, setPdfView] = useState<'original' | 'text'>('original');
  const [previewRevision, setPreviewRevision] = useState(0);
  const [view, setView] = useState<'document' | 'history'>('document');
  const [dialog, setDialog] = useState<'project' | 'location' | null>(null);
  const [sidebar, setSidebar] = useState(() => window.innerWidth > 640);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [watching, setWatching] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const currentProject = useRef(projectId); currentProject.current = projectId;
  const documentRequest = useRef(0);
  const navigationRequest = useRef(0);
  const pendingChanges = useRef({ running: false, dirty: false, all: false, paths: new Set<string>() });
  const refresh = useRef<(paths?: string[]) => Promise<void>>(async () => {});
  const project = projects.find(item => item.id === projectId);
  const workspace = project?.workspace.split(/[\\/]/).at(-1) || 'workspace';
  const documentTitle = files.find(file => file.path === (openingFile || document?.path))?.title || (!openingFile && document?.title) || (openingFile || document?.path)?.split('/').at(-1) || '项目材料';

  useEffect(() => {
    const controller = new AbortController();
    void api<{ projects: Project[]; errors: { name: string; error: string }[] }>('/projects', { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      setProjects(result.projects);
      if (currentProject.current && !result.projects.some(item => item.id === currentProject.current)) setProjectId('');
      if (result.errors.length) setError(result.errors.map(item => `${item.name}：${item.error}`).join('\n'));
    }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const narrow = window.matchMedia('(max-width:640px)');
    const collapse = () => { if (narrow.matches) setSidebar(false); };
    narrow.addEventListener('change', collapse);
    return () => narrow.removeEventListener('change', collapse);
  }, []);

  useEffect(() => {
    try { localStorage.setItem('co-math-project', projectId); } catch { /* Reading works without browser storage. */ }
    setFiles([]); setDocument(null); setSelectedFile(null); setOpeningFile(null); setError(''); setCopied(false);
    setView('document'); setPdfPage(1); setWatching(false); setRefreshing(false);
    const initialRequest = ++documentRequest.current;
    pendingChanges.current = { running: false, dirty: false, all: false, paths: new Set() };
    if (!projectId) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    void api<Project>(`/projects/${projectId}`, { signal: controller.signal }).then(updated => {
      if (controller.signal.aborted) return;
      setProjects(old => [...old.filter(item => item.id !== updated.id), updated]);
      if (documentRequest.current === initialRequest) void openFile(`${updated.workspace.split(/[\\/]/).at(-1)}/project/PROJECT.md`, projectId);
    }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    const events = new EventSource(`/api/projects/${projectId}/events`);
    events.onopen = () => { if (!controller.signal.aborted) { setWatching(true); void refresh.current(); } };
    events.onmessage = event => {
      if (controller.signal.aborted) return;
      try {
        const change = JSON.parse(event.data);
        if (change.type === 'watch-unavailable') setWatching(false);
        if (change.type === 'files-changed') void refresh.current(change.paths);
      } catch { setWatching(false); }
    };
    events.onerror = () => { if (!controller.signal.aborted) setWatching(false); };
    const onFocus = () => { if (!controller.signal.aborted) void refresh.current(); };
    window.addEventListener('focus', onFocus);
    return () => { controller.abort(); events.close(); window.removeEventListener('focus', onFocus); };
  }, [projectId]);

  async function openFile(path: string, id = projectId, selection: MaterialSelection | null = null, background = false) {
    const request = ++documentRequest.current;
    if (!background) {
      setOpeningFile(path); setSelectedFile({ path, selection }); setView('document'); setError('');
      setPdfPage(selection?.startPage || 1); setPdfView(selection ? 'text' : 'original');
    }
    const query = new URLSearchParams({ path });
    if (selection) for (const [key, value] of Object.entries(selection)) if (value !== undefined) query.set(key, String(value));
    try {
      const data = await api<Document>(`/projects/${id}/file?${query}`);
      if (request !== documentRequest.current || currentProject.current !== id) return;
      setDocument(data); setError('');
      if (!background) {
        if (window.innerWidth <= 640) setSidebar(false);
      }
      setPreviewRevision(old => old + 1);
    } catch (reason) {
      if (request === documentRequest.current && currentProject.current === id) {
        setDocument(null); setError((reason as Error).message);
      }
    } finally {
      if (request === documentRequest.current && currentProject.current === id) setOpeningFile(null);
    }
  }

  async function refreshFiles(paths?: string[]) {
    const id = projectId;
    if (!id) return;
    const pending = pendingChanges.current;
    pending.dirty = true;
    if (!paths?.length) pending.all = true;
    else for (const path of paths) pending.paths.add(path);
    if (pending.running) return;
    pending.running = true; pending.dirty = false;
    const changes = { all: pending.all, paths: [...pending.paths] };
    pending.all = false; pending.paths.clear();
    const reading = documentRequest.current;
    setRefreshing(true);
    try {
      const updated = await api<Project>(`/projects/${id}`);
      if (currentProject.current !== id || pendingChanges.current !== pending) return;
      setProjects(old => [...old.filter(item => item.id !== id), updated]);
      setFileRevision(old => old + 1);
      const changed = changes.all || changes.paths.some(path => selectedFile?.path === path || selectedFile?.path.startsWith(path + '/'));
      if (view === 'document' && selectedFile && changed && reading === documentRequest.current) await openFile(selectedFile.path, id, selectedFile.selection, true);
    } catch (reason) {
      if (currentProject.current === id && pendingChanges.current === pending) setError((reason as Error).message);
    } finally {
      pending.running = false;
      if (currentProject.current === id && pendingChanges.current === pending) {
        setRefreshing(false);
        if (pending.dirty) void refresh.current(pending.all ? undefined : [...pending.paths]);
      }
    }
  }
  refresh.current = refreshFiles;

  function openProjectDialog() {
    navigationRequest.current++;
    setDialog('project');
  }

  async function selectProject(item: Project) {
    const request = ++navigationRequest.current;
    try {
      const opened = await api<Project>('/projects/open', { method: 'POST', body: { path: item.path } });
      if (request !== navigationRequest.current) return;
      setProjects(old => [...old.filter(previous => previous.id !== opened.id), opened]);
      setProjectId(opened.id);
    } catch (reason) { if (request === navigationRequest.current) setError((reason as Error).message); }
  }

  async function copyPath() {
    try { await navigator.clipboard.writeText(project?.path || ''); setCopied(true); }
    catch { setError('无法自动复制，可以在项目位置中选中路径复制。'); }
  }

  function showHistory() {
    documentRequest.current++; setOpeningFile(null); setView('history'); setError('');
    if (window.innerWidth <= 640) setSidebar(false);
  }

  return <div className={'app visualizer ' + (sidebar ? '' : 'sidebar-hidden')}>
    <nav className="sidebar" id="project-sidebar">
      <a className="brand" href="#" aria-label="VeryMath Co-Math 首页" onClick={event => { event.preventDefault(); navigationRequest.current++; setProjectId(''); }}>
        <img className="brand-logo" src={verymathLogo} alt="VeryMath" width={960} height={286}/><span className="brand-caption">Co-Math · 研究阅读器</span>
      </a>
      <button className="new-project" onClick={openProjectDialog}><FolderOpen size={16}/>打开项目</button>
      <div className="sidebar-label">研究项目<span>{projects.length.toString().padStart(2, '0')}</span></div>
      <div className="project-list">{projects.map(item => <button title={item.path} className={'project-item ' + (item.id === projectId ? 'active' : '')} key={item.id} onClick={() => void selectProject(item)}><FolderOpen size={15}/><span>{item.name}</span>{item.id === projectId && <span className="active-pin"/>}</button>)}{!projects.length && <p className="sidebar-hint">打开 coding agent 中的研究项目。</p>}</div>
      {project && <><div className="sidebar-label materials-label">项目文件</div><FileBrowser key={projectId} project={project} revision={fileRevision} activePath={view === 'document' ? document?.path : undefined} onOpen={path => { void openFile(path); }} onFiles={setFiles}/></>}
      <div className="sidebar-bottom"><span className="local-dot"/><span>文件保存在本机 · 网页只读</span></div>
    </nav>
    {sidebar && <button className="sidebar-dismiss" aria-label="关闭文件侧栏" onClick={() => setSidebar(false)}/>}
    {sidebar && <PanelResizer panel="sidebar" controls="project-sidebar"/>}
    <main className="workbench">
      <header className="topbar">
        <div className="breadcrumbs"><button className="icon-button" aria-label={sidebar ? '收起侧栏' : '展开侧栏'} onClick={() => setSidebar(!sidebar)}><PanelLeftClose size={18}/></button><span>研究项目</span><ChevronRight size={14}/><strong>{project?.name || 'Co-Math'}</strong></div>
        {project && <div className="topbar-right"><span className="sync-status">{watching ? '文件自动更新' : '返回页面时刷新'}</span><button className="icon-button" disabled={refreshing} aria-label="刷新项目" title="刷新项目文件" onClick={() => void refreshFiles()}><RefreshCw size={16} className={refreshing ? 'refreshing' : ''}/></button><button className="icon-button" aria-label="项目位置" title="项目位置" onClick={() => { setCopied(false); setDialog('location'); }}><FolderOpen size={17}/></button></div>}
      </header>
      {error && <div className="banner error" role="alert"><span>{error}</span><button aria-label="关闭错误" onClick={() => setError('')}><X size={15}/></button></div>}
      {!project ? <section className="welcome"><div className="welcome-content"><span className="eyebrow">YOUR RESEARCH, ON THE PAGE</span><h1>把研究，<br/>读得更清楚。</h1><p>在 coding agent 中推进研究，<br/>在这里阅读论文、推导与结果。</p><button className="primary welcome-button" onClick={openProjectDialog}><FolderOpen size={18}/>打开研究项目<ArrowUpRight size={18}/></button><p className="welcome-help">还没有项目？在 coding agent 中说：<br/><q>请用 Co-Math 为我新建一个研究项目。</q></p></div></section> : <>
        <nav className="project-navigation" aria-label="项目文档">
          {[['项目说明', 'PROJECT.md'], ['研究目标', 'GOALS.yaml'], ['进展记录', 'PROJECT_STATUS.md']].map(([label, name]) => <button key={name} className={view === 'document' && document?.path === `${workspace}/project/${name}` ? 'active' : ''} onClick={() => void openFile(`${workspace}/project/${name}`)}>{label}</button>)}
          {project.latest_note && <button className={view === 'document' && document?.path === project.latest_note ? 'active' : ''} onClick={() => void openFile(project.latest_note!)}>最近笔记</button>}
          <button className={'history-link ' + (view === 'history' ? 'active' : '')} onClick={showHistory}><History size={14}/>历史讨论</button>
        </nav>
        {view === 'history' ? <ConversationHistory key={projectId} projectId={projectId}/> : <section className="document-pane">
          <div className="document-toolbar"><div><FileText size={15}/><span>{documentTitle}</span></div>{document && !openingFile && <a className="download-document" href={`/api/projects/${projectId}/download?path=${encodeURIComponent(document.path)}`} download title="下载原文件"><Download size={14}/><span>原文件</span></a>}</div>
          <div className="document-scroll"><div className={'reading-page ' + (/\.pdf$/i.test(document?.path || '') ? 'reading-pdf' : '')}>
            {openingFile ? <div className="document-empty" role="status"><BookOpen size={28}/><h3>正在打开材料…</h3></div> : document ? <>
              {/\.pdf$/i.test(document.path) && <div className="material-original-actions"><div className="pdf-view-tabs"><button className={pdfView === 'original' ? 'selected' : ''} onClick={() => setPdfView('original')}>原文</button><button className={pdfView === 'text' ? 'selected' : ''} onClick={() => setPdfView('text')}>提取文字</button></div></div>}
              {document.format !== 'goals' && (!/\.pdf$/i.test(document.path) || pdfView === 'text') && (!!document.paragraphCount || !!document.pageCount) && <MaterialRange key={'range-' + document.path + (document.selectionLabel || '')} document={document} currentPage={pdfPage} onApply={selection => openFile(document.path, projectId, selection)}/>}
              {document.note && (pdfView === 'text' || !/\.pdf$/i.test(document.path)) && <p className="material-reading-note">{document.note}</p>}
              {document.format === 'goals' ? <GoalsView document={document}/> : /\.pdf$/i.test(document.path) && pdfView === 'original' ? <Suspense fallback={<p className="muted">正在打开 PDF…</p>}><PdfPreview url={`/api/projects/${projectId}/preview?path=${encodeURIComponent(document.path)}&revision=${previewRevision}`} initialPage={pdfPage} onPageChange={setPdfPage}/></Suspense> : <TextDocument key={'text-' + document.path + (document.selectionLabel || '')} document={document}/>}
              <footer className="document-end"><span>项目中的原始记录{document.selectionLabel ? ` · ${document.selectionLabel}` : ''}</span><code>{document.path}</code></footer>
            </> : <div className="document-empty"><BookOpen size={28}/><h3>{loading ? '正在读取项目…' : '选择一份材料'}</h3><p>从左侧打开论文、笔记或研究结果。</p></div>}
          </div></div>
        </section>}
      </>}
    </main>
    {dialog === 'project' && <ProjectDialog projects={projects} onClose={() => setDialog(null)} onOpened={item => { navigationRequest.current++; setProjects(old => [...old.filter(previous => previous.id !== item.id), item]); setProjectId(item.id); setDialog(null); }}/ >}
    {dialog === 'location' && project && <Modal title="项目位置" onClose={() => setDialog(null)}><p className="project-location-help">在 coding agent 中打开这个文件夹，继续同一项研究。</p><div className="project-location-path"><code>{project.path}</code><button aria-label="复制项目路径" onClick={() => void copyPath()}>{copied ? <Check size={16}/> : <Copy size={16}/>}</button></div><p className="form-help">网页展示已保存的文件。研究任务、计算和修改继续在 coding agent 中进行。</p></Modal>}
  </div>;
}
