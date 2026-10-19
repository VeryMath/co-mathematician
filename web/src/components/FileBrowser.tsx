import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { ArrowUp, FileText, FolderOpen, Search } from 'lucide-react';
import { api, type Project, type ProjectFile, type ProjectFilesPage } from '../api';

export function FileBrowser({ project, revision, activePath, onOpen, onFiles }: {
  project: Project; revision: number; activePath?: string;
  onOpen: (path: string) => void; onFiles: Dispatch<SetStateAction<ProjectFile[]>>;
}) {
  const workspace = project.workspace.split(/[\\/]/).at(-1)!;
  const [directory, setDirectory] = useState(`${workspace}/project`);
  const [query, setQuery] = useState(''); const [page, setPage] = useState<ProjectFilesPage | null>(null);
  const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);

  function remember(files: ProjectFile[]) {
    onFiles(old => [...new Map([...old, ...files].map(file => [file.path, file])).values()]);
  }
  function endpoint(offset = 0) {
    return `/projects/${project.id}/files?` + new URLSearchParams({ directory, query, offset: String(offset), limit: '100' });
  }
  useEffect(() => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setPage(null); setError('');
    const timer = setTimeout(() => {
      void api<ProjectFilesPage>(endpoint(), { signal: controller.signal }).then(data => {
        if (controller.signal.aborted) return;
        setPage(data); remember(data.files);
      }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, query ? 250 : 0);
    return () => { clearTimeout(timer); request.current?.abort(); };
  }, [project.id, directory, query, revision, onFiles]);

  async function more() {
    if (loading || page?.nextOffset == null) return;
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError('');
    try {
      const data = await api<ProjectFilesPage>(endpoint(page.nextOffset), { signal: controller.signal });
      if (controller.signal.aborted) return;
      setPage(old => old ? { ...data,
        files: [...new Map([...old.files, ...data.files].map(file => [file.path, file])).values()],
        directories: [...new Map([...old.directories, ...data.directories].map(folder => [folder.path, folder])).values()],
      } : data);
      remember(data.files);
    } catch (reason) { if (!controller.signal.aborted) setError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  function navigate(path: string) { setQuery(''); setDirectory(path); }
  function fileButton(file: ProjectFile) {
    return <button title={file.path} className={'file-item ' + (activePath === file.path ? 'active' : '')} key={file.path} onClick={() => onOpen(file.path)}>
      <FileText size={14}/><span>{file.title || file.path.split('/').at(-1)}{query && <small>{file.path}</small>}</span>
    </button>;
  }
  const showAll = !!query.trim() || directory.startsWith('.agents/');
  return <div className="file-browser">
    <label className="file-search"><Search size={13}/><input aria-label="搜索项目文件名" placeholder="搜索整个项目的文件名…" maxLength={200} value={query} onChange={event => setQuery(event.target.value)}/></label>
    <div className="file-roots"><button onClick={() => navigate(workspace)}>研究文件</button><button onClick={() => navigate('.agents/skills')}>项目方法</button></div>
    <div className="file-location"><button aria-label="材料目录上一级" disabled={!page?.parent || !!query.trim()} onClick={() => page?.parent && navigate(page.parent)}><ArrowUp size={13}/></button><span title={directory}>{query.trim() ? '整个项目的搜索结果' : directory}</span></div>
    <div className="file-list">
      {page?.directories.map(folder => <button className="file-item folder-item" key={folder.path} title={folder.path} onClick={() => navigate(folder.path)}><FolderOpen size={14}/><span>{folder.name}</span></button>)}
      {page?.files.filter(file => showAll || !file.internal).map(fileButton)}
      {!showAll && page?.files.some(file => file.internal) && <details className="internal-files"><summary>高级文件</summary>{page.files.filter(file => file.internal).map(fileButton)}</details>}
      {page && !page.files.length && !page.directories.length && <p className="file-browser-message">{query.trim() ? '没有找到这个文件名。' : '这个目录暂无研究材料。'}</p>}
      {page?.hasMore && <button className="load-files" disabled={loading} onClick={() => void more()}>加载更多</button>}
      {loading && <p role="status" className="file-browser-message">正在读取材料…</p>}
      {error && <p role="alert" className="error file-browser-message">{error}</p>}
      {page?.warnings?.map(warning => <p key={warning} className="file-browser-message">{warning}</p>)}
    </div>
  </div>;
}
