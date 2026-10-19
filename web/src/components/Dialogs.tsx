import { useEffect, useRef, useState, type ReactNode, type FormEvent } from 'react';
import { X } from 'lucide-react';
import { api, type Project } from '../api';
import { ProjectPicker } from './ProjectPicker';

export function Modal({ title, children, onClose, className }: { title: string; children: ReactNode; onClose: () => void; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className={className} onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="dialog-header"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={20}/></button></header>{children}
  </dialog>;
}

export function ProjectDialog({ onClose, onOpened, projects }: { onClose: () => void; onOpened: (project: Project) => void; projects: Project[] }) {
  const [path, setPath] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function openProject(location: string) {
    if (busy || !location) return;
    setBusy(true); setError('');
    try { onOpened(await api<Project>('/projects/open', { method: 'POST', body: { path: location } })); }
    catch (error) { setError((error as Error).message); setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    void openProject(path);
  }
  return <Modal title="打开研究项目" onClose={() => { if (!busy) onClose(); }}><form onSubmit={submit}>
    <ProjectPicker projects={projects} disabled={busy} onSelect={setPath} onOpen={location => void openProject(location)}/>
    {error && <p role="alert" className="error">{error}</p>}
    <footer className="dialog-footer"><button type="button" disabled={busy} className="secondary" onClick={onClose}>取消</button><button disabled={busy || !path} className="primary">{busy ? '正在打开…' : '打开项目'}</button></footer>
  </form></Modal>;
}
