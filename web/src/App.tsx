import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { BookOpen, ChevronRight, FileText, FolderOpen, Plus, Settings, RefreshCw, PanelLeftClose, NotebookPen, X, ArrowUpRight, Check, Upload, Download } from 'lucide-react';
import { api, mergeMessages, type Document, type Message, type ModelSettings, type Project, type ProjectFile, type ImportedMaterial, type Skill, type MaterialSelection } from './api';
import { TextDocument } from './components/TextDocument';
import { ProjectDialog, NoteDialog } from './components/Dialogs';
import { SettingsDialog } from './components/SettingsDialog';
import { Chat } from './components/Chat';
import { MaterialsDialog } from './components/MaterialsDialog';
import { SkillsDialog } from './components/SkillsDialog';
import { GoalsView } from './components/GoalsView';
import { PanelResizer } from './components/PanelResizer';
import { FileBrowser } from './components/FileBrowser';
import { MaterialRange } from './components/MaterialRange';
import { ProjectResume } from './components/ProjectResume';
import verymathLogo from './assets/verymath-logo.png?inline';

const PdfPreview = lazy(() => import('./components/PdfPreview'));

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]); const [home, setHome] = useState('');
  const [projectId, setProjectId] = useState(() => localStorage.getItem('co-math-project') || '');
  const [files, setFiles] = useState<ProjectFile[]>([]); const [selected, setSelected] = useState<string[]>([]);
  const [fileRevision, setFileRevision] = useState(0);
  const [ranges, setRanges] = useState<Record<string, MaterialSelection>>({});
  const [pdfPage, setPdfPage] = useState(1);
  const [document, setDocument] = useState<Document | null>(null); const [messages, setMessages] = useState<Message[]>([]);
  const [pdfView, setPdfView] = useState<'original' | 'text'>('original');
  const [openingFile, setOpeningFile] = useState<string | null>(null);
  const [settings, setSettings] = useState<ModelSettings | null>(null); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [dialog, setDialog] = useState<'project' | 'settings' | 'note' | 'materials' | 'skills' | null>(null); const [note, setNote] = useState('');
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [initialMaterials, setInitialMaterials] = useState<File[]>([]);
  const [draggingMaterials, setDraggingMaterials] = useState(false); const dragDepth = useRef(0);
  const [sending, setSending] = useState(false); const [connected, setConnected] = useState(false); const [loading, setLoading] = useState(false);
  const [switchingModel, setSwitchingModel] = useState(false);
  const [sidebar, setSidebar] = useState(() => window.innerWidth >= 960); const [mobilePane, setMobilePane] = useState('document');
  const currentProject = useRef(projectId); currentProject.current = projectId;
  const documentRequest = useRef(0);
  const project = projects.find(p => p.id === projectId);
  const documentTitle = files.find(file => file.path === (openingFile || document?.path))?.title || (!openingFile && document?.title) || (openingFile || document?.path)?.split('/').at(-1) || '项目材料';
  const busy = messages.some(m => m.status === 'running');
  async function reloadProjects() {
    const result = await api<{ projects: Project[]; home: string; errors: { name: string; error: string }[] }>('/projects');
    setProjects(result.projects); setHome(result.home);
    if (result.errors.length) setError(result.errors.map(e => `${e.name}：${e.error}`).join('\n'));
  }
  async function refreshProject(id: string) {
    const updated = await api<Project>(`/projects/${id}`);
    if (currentProject.current === id) setProjects(old => [...old.filter(item => item.id !== id), updated]);
    return updated;
  }
  useEffect(() => { void Promise.all([reloadProjects(), api<ModelSettings>('/settings').then(setSettings)]).catch(e => setError(e.message)); }, []);
  useEffect(() => {
    const narrow = window.matchMedia('(max-width:640px)');
    const collapse = () => { if (narrow.matches) setSidebar(false); };
    narrow.addEventListener('change', collapse);
    return () => narrow.removeEventListener('change', collapse);
  }, []);
  useEffect(() => {
    localStorage.setItem('co-math-project', projectId);
    setFiles([]); setSelected([]); setRanges({}); setPdfPage(1); setMessages([]); setDocument(null); setError(''); setNotice('');
    setMobilePane('document');
    setSelectedSkill(null);
    setOpeningFile(null);
    setDraggingMaterials(false); dragDepth.current = 0;
    documentRequest.current++; setConnected(false);
    const initialDocumentRequest = documentRequest.current;
    if (!projectId) return;
    const controller = new AbortController(); const options = { signal: controller.signal };
    const prefix = `/projects/${projectId}`;
    setLoading(true);
    Promise.all([api<Project>(prefix, options), api<{ messages: Message[] }>(prefix + '/chat', options)]).then(([updated, conversation]) => {
      if (controller.signal.aborted) return;
      setProjects(old => [...old.filter(item => item.id !== updated.id), updated]);
      setMessages(old => mergeMessages(old, conversation.messages));
      if (documentRequest.current === initialDocumentRequest) void openFile(`${updated.workspace.split(/[\\/]/).at(-1)}/project/PROJECT.md`, projectId, false, null);
    }).catch(e => { if (!controller.signal.aborted) setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    const events = new EventSource('/api' + prefix + '/events');
    events.onopen = () => {
      if (controller.signal.aborted) return;
      setConnected(true);
      void api<{ messages: Message[] }>(prefix + '/chat', options).then(data => { if (!controller.signal.aborted) setMessages(old => mergeMessages(old, data.messages)); }).catch(() => {});
    };
    events.onmessage = event => { if (!controller.signal.aborted) { const message: Message = JSON.parse(event.data); setMessages(old => mergeMessages(old, [message])); if (message.status && message.status !== 'running') void refreshProject(projectId).catch(() => {}); } };
    events.onerror = () => { if (!controller.signal.aborted) setConnected(false); };
    return () => { controller.abort(); events.close(); };
  }, [projectId]);
  async function openFile(path: string, id = projectId, showDocument = true, selection: MaterialSelection | null = ranges[path] || null) {
    const request = ++documentRequest.current;
    setOpeningFile(path);
    const query = new URLSearchParams({ path });
    if (selection) for (const [key, value] of Object.entries(selection)) if (value !== undefined) query.set(key, String(value));
    try { const data = await api<Document>(`/projects/${id}/file?${query}`); if (request === documentRequest.current && currentProject.current === id) {
      setDocument(data); setPdfPage(data.selection?.startPage || 1); setPdfView(selection ? 'text' : 'original');
      setRanges(old => { const next = { ...old }; if (data.selection) next[path] = data.selection; else delete next[path]; return next; });
      if (showDocument) { setMobilePane('document'); if (window.innerWidth <= 640) setSidebar(false); }
    } }
    catch (e) { if (request === documentRequest.current) setError((e as Error).message); }
    finally { if (request === documentRequest.current && currentProject.current === id) setOpeningFile(null); }
  }
  async function send(content: string) {
    setSending(true); setError(''); const id = projectId;
    try {
      await api(`/projects/${id}/runs`, { method: 'POST', body: { content, files: selected, ranges: Object.fromEntries(selected.filter(path => ranges[path]).map(path => [path, ranges[path]])), profileId: settings?.activeProfileId, model: settings?.model, provider: settings?.provider, baseUrl: settings?.baseUrl, skill: selectedSkill ? { source: selectedSkill.source, path: selectedSkill.path, directory: selectedSkill.directory } : undefined } });
      const conversation = await api<{ messages: Message[] }>(`/projects/${id}/chat`);
      if (currentProject.current === id) setMessages(old => mergeMessages(old, conversation.messages));
    } catch (e) { setError((e as Error).message); void api<ModelSettings>('/settings').then(setSettings).catch(() => {}); throw e; } finally { setSending(false); }
  }
  async function selectModel(profileId: string, model?: string) {
    if (switchingModel) return;
    setSwitchingModel(true); setError('');
    try {
      const value = await api<ModelSettings>('/settings/select', { method: 'POST', body: { profileId, model } });
      setSettings(value);
    } catch (error) { setError((error as Error).message); }
    finally { setSwitchingModel(false); }
  }
  async function saveNote(title: string, content: string) {
    const id = projectId;
    const saved = await api<Document>(`/projects/${id}/notes`, { method: 'POST', body: { title, content } });
    if (currentProject.current !== id) return;
    documentRequest.current++; setOpeningFile(null); setDocument({ ...saved, title }); setDialog(null); setNotice('研究笔记已保存到项目。');
    setFileRevision(old => old + 1);
    await refreshProject(id);
  }
  async function refreshFiles() {
    const id = projectId;
    try {
      setFileRevision(old => old + 1);
      await refreshProject(id);
      if (currentProject.current !== id) return;
      if (document) void openFile(document.path, id);
    } catch (error) { if (currentProject.current === id) setError((error as Error).message); }
  }
  function addMaterials(incoming: File[] = []) { setInitialMaterials(incoming); setDialog('materials'); }
  async function materialsAdded(id: string, materials: ImportedMaterial[]) {
    if (currentProject.current !== id) return;
    setFileRevision(old => old + 1);
    if (materials[0]) await openFile(materials[0].path, id, true, null);
  }
  return <div className={'app ' + (sidebar ? '' : 'sidebar-hidden')}>
    <nav className="sidebar" id="project-sidebar">
      <a className="brand" href="#" aria-label="VeryMath Co-Math 首页" onClick={e => { e.preventDefault(); setProjectId(''); }}><img className="brand-logo" src={verymathLogo} alt="VeryMath" width={960} height={286}/><span className="brand-caption">Co-Math · 研究工作台</span></a>
      <button className="new-project" onClick={() => setDialog('project')}><Plus size={17}/>新建 / 打开项目</button>
      <div className="sidebar-label">我的研究 <span>{projects.length.toString().padStart(2, '0')}</span></div>
      <div className="project-list">{projects.map(p => <button title={p.path} className={'project-item ' + (p.id === projectId ? 'active' : '')} key={p.id} onClick={() => setProjectId(p.id)}><FolderOpen size={16}/><span>{p.name}</span>{p.id === projectId && <span className="active-pin"/>}</button>)}{!projects.length && <p className="sidebar-hint">每个问题，都有自己的研究空间。</p>}</div>
      {project && <><div className="sidebar-label materials-label">项目材料<span className="material-list-actions"><button aria-label="添加材料" title="添加材料" onClick={() => addMaterials()}><Plus size={15}/></button><button aria-label="刷新材料" onClick={() => void refreshFiles()}><RefreshCw size={13}/></button></span></div><FileBrowser key={projectId} project={project} revision={fileRevision} activePath={document?.path} selected={selected} onOpen={path => { void openFile(path); }} onFiles={setFiles}/></>}
      <div className="sidebar-bottom"><span className="local-dot"/><span>本机保存 · 持续研究</span><button aria-label="模型设置" onClick={() => setDialog('settings')}><Settings size={16}/></button></div>
    </nav>
    {sidebar && <PanelResizer panel="sidebar" controls="project-sidebar"/>}
    <main className={'workbench show-' + mobilePane}>
      <header className="topbar"><div className="breadcrumbs"><button className="icon-button" aria-label={sidebar ? '收起侧栏' : '展开侧栏'} onClick={() => setSidebar(!sidebar)}><PanelLeftClose size={18}/></button><span>研究空间</span><ChevronRight size={14}/><strong>{project?.name || '欢迎回来'}</strong></div><div className="topbar-right"><span className="local-badge"><span className="local-dot"/>LOCAL</span><button className="icon-button" onClick={() => setDialog('settings')} aria-label="打开设置"><Settings size={18}/></button></div></header>
      {error && <div className="banner error" role="alert"><span>{error}</span><button aria-label="关闭错误" onClick={() => setError('')}><X size={15}/></button></div>}
      {notice && <div className="banner notice" role="status"><span>{notice}</span><button aria-label="关闭提示" onClick={() => setNotice('')}><X size={15}/></button></div>}
      {project && <ProjectResume key={projectId} project={project} onOpen={path => { void openFile(path); }}/ >}
      {!project ? <section className="welcome"><div className="welcome-content"><span className="eyebrow">A PLACE FOR MATHEMATICAL THOUGHT</span><h1>让问题，<br/>一步步变得清楚。</h1><p>把想法、推导与未解决的问题留在同一个地方。<br/>与模型讨论，回到材料，继续你的研究。</p><button className="primary welcome-button" onClick={() => setDialog('project')}><Plus size={18}/>开启研究空间<ArrowUpRight size={18}/></button><div className="welcome-features"><div><BookOpen size={20}/><strong>读懂材料</strong><span>从项目文档出发</span></div><div><NotebookPen size={20}/><strong>留下思考</strong><span>笔记属于你的项目</span></div><div><RefreshCw size={20}/><strong>随时继续</strong><span>重新打开，接着研究</span></div></div></div><div className="math-decoration" aria-hidden="true"><span>∇f(x)</span><i>思考 · 推导 · 再检视</i><div>f(x) − f(x*) ≤ ε</div></div></section> : <><div className="mobile-tabs"><button className={mobilePane === 'document' ? 'active' : ''} onClick={() => setMobilePane('document')}>研究材料</button><button className={mobilePane === 'chat' ? 'active' : ''} onClick={() => setMobilePane('chat')}>模型对话</button></div><div className={'workspace-columns ' + (draggingMaterials ? 'dragging-materials' : '')}
        onDragEnter={event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); dragDepth.current++; setDraggingMaterials(true); } }}
        onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }}
        onDragLeave={event => { if (event.dataTransfer.types.includes('Files')) { dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDraggingMaterials(false); } }}
        onDrop={event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); dragDepth.current = 0; setDraggingMaterials(false); addMaterials([...event.dataTransfer.files]); } }}>
        {draggingMaterials && <div className="workspace-drop-hint"><Upload size={25}/><strong>松开文件，添加到当前项目</strong></div>}<section className="document-pane">
        <div className="document-toolbar"><div><FileText size={16}/><span>{documentTitle}</span></div><div className="document-tools"><button className="text-button" onClick={() => addMaterials()}><Upload size={14}/>添加材料</button><button className="text-button" onClick={() => { setNote(''); setDialog('note'); }}><Plus size={15}/>写笔记</button></div></div>
        <div className="document-scroll">{openingFile ? <div className="document-empty" role="status"><BookOpen size={28}/><h3>正在打开材料…</h3></div> : document ? <><div className="document-heading"><span className="eyebrow">{document.format === 'goals' ? 'RESEARCH GOALS' : 'RESEARCH MATERIAL'}</span><button className={'attach-button ' + (selected.includes(document.path) ? 'attached' : '')} disabled={document.readable === false || (!selected.includes(document.path) && selected.length >= 6)} onClick={() => setSelected(old => old.includes(document.path) ? old.filter(p => p !== document.path) : [...old, document.path])}>{selected.includes(document.path) ? <Check size={14}/> : <Plus size={14}/>} {selected.includes(document.path) ? '已加入对话' : '结合此文档提问'}</button></div>
          {document.format !== 'goals' && (!!document.paragraphCount || !!document.pageCount) && <MaterialRange key={document.path + (document.selectionLabel || '')} document={document} currentPage={pdfPage} onApply={selection => openFile(document.path, projectId, true, selection)}/>}
          {(document.path.includes('/project/materials/') || /\.(pdf|docx)$/i.test(document.path)) && <div className="material-original-actions">{/\.pdf$/i.test(document.path) && <div className="pdf-view-tabs"><button className={pdfView === 'original' ? 'selected' : ''} onClick={() => setPdfView('original')}>原文</button><button className={pdfView === 'text' ? 'selected' : ''} onClick={() => setPdfView('text')}>提取文字</button></div>}<a href={`/api/projects/${projectId}/download?path=${encodeURIComponent(document.path)}`} download><Download size={14}/>下载原文件</a></div>}{document.note && <p className="material-reading-note">{document.note}</p>}
          {document.format === 'goals' ? <GoalsView document={document}/> : /\.pdf$/i.test(document.path) && pdfView === 'original' ? <Suspense fallback={<p className="muted">正在打开 PDF…</p>}><PdfPreview url={`/api/projects/${projectId}/preview?path=${encodeURIComponent(document.path)}`} initialPage={pdfPage} onPageChange={setPdfPage}/></Suspense> : <TextDocument key={document.path + (document.selectionLabel || '')} document={document}/>}{document.format !== 'goals' && <footer className="document-end"><span>来自项目文件{document.selectionLabel ? ` · ${document.selectionLabel}` : ''}</span><code>{document.path}</code></footer>}</> : <div className="document-empty"><BookOpen size={28}/><h3>{loading ? '正在读取项目…' : '选择一份材料'}</h3><p>左侧可浏览目录，也可以搜索项目中的文件名。</p></div>}</div>
      </section><PanelResizer key={`divider-${projectId}`} panel="chat" controls="research-chat"/><Chat key={projectId} selectedSkill={selectedSkill} onSkills={() => setDialog('skills')} onClearSkill={() => setSelectedSkill(null)} messages={messages} settings={settings} files={selected} ranges={ranges} busy={busy} sending={sending || switchingModel} switchingModel={switchingModel} onSelectModel={selectModel} connected={connected} onSend={send} onStop={() => { void api(`/projects/${projectId}/cancel`, { method: 'POST', body: {} }).catch(e => setError(e.message)); }} onSave={content => { setNote(content); setDialog('note'); }} onRemoveFile={path => setSelected(old => old.filter(p => p !== path))} onSettings={() => setDialog('settings')}/></div></>}
    </main>
    {dialog === 'project' && <ProjectDialog home={home} projects={projects} onClose={() => setDialog(null)} onCreated={p => { setProjects(old => [...old.filter(item => item.id !== p.id), p]); setProjectId(p.id); setDialog(null); }}/ >}
    {dialog === 'settings' && settings && <SettingsDialog settings={settings} onClose={() => setDialog(null)} onChanged={setSettings}/ >}
    {dialog === 'note' && project && <NoteDialog initial={note} onClose={() => setDialog(null)} onSave={saveNote}/ >}
    {dialog === 'materials' && project && <MaterialsDialog key={projectId} projectId={projectId} projectName={project.name} initialFiles={initialMaterials} onClose={() => setDialog(null)} onAdded={materialsAdded}/>}
    {dialog === 'skills' && project && <SkillsDialog key={projectId} projectId={projectId} onLibraryChanged={() => setSelectedSkill(old => old?.source === 'verymath' ? null : old)} onClose={() => setDialog(null)} onUse={skill => { setSelectedSkill(skill); setDialog(null); setMobilePane('chat'); }}/ >}
  </div>;
}
