export interface Project { id: string; name: string; path: string; workspace: string; status: string; question: string; blocker: string; recent_update?: string; open_question?: string; next_action?: string; resume_prompt?: string; latest_note?: string; }
export interface ProjectFolders { path: string; name: string; parent: string | null; folders: { name: string; path: string }[]; shortcuts: { name: string; path: string }[]; projectName: string; projectError: string; truncated: boolean; }
export interface ProjectFile { path: string; size: number; title?: string; internal?: boolean; }
export interface ProjectFilesPage { files: ProjectFile[]; directories: { path: string; name: string }[]; directory: string; parent: string | null; nextOffset: number | null; hasMore: boolean; warnings?: string[]; }
export interface MaterialSelection { startPage?: number; endPage?: number; startParagraph?: number; endParagraph?: number; }
export interface GoalView { question: string; questionStatus: string; language: string; goals: { id: string; title: string; status: string; details: { label: string; content: string }[] }[]; }
export interface Document { path: string; content: string; title?: string; format?: 'markdown' | 'text' | 'goals'; readable?: boolean; truncated?: boolean; note?: string; pageCount?: number; paragraphCount?: number; selection?: MaterialSelection; selectionLabel?: string; rawContent?: string; goalsView?: GoalView; }
export interface Skill { source: 'project' | 'verymath'; path: string; directory?: string; name: string; title: string; description?: string; group?: string; mode?: 'guidance'; resources?: string[]; warnings?: string[]; }
export interface SkillDetail extends Omit<Skill, 'resources'> { instructions: string; resources: { path: string; content: string }[]; warnings: string[]; }
export interface SkillCatalog { directory: string; skills: Skill[]; warnings: string[]; truncated: boolean; mode: 'guidance'; }
export interface Message { id: string; order: number; role: 'user' | 'assistant'; content: string; createdAt: string; status?: 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'; model?: string; profileName?: string; provider?: string; sources?: string[]; sourceNotes?: string[]; skill?: Skill; error?: string; }
export interface ImportedMaterial { path: string; name: string; size: number; }
export interface ModelOption { id: string; name: string; }
export interface ModelProfile { id: string; name: string; provider: string; model: string; baseUrl: string; models: string[]; configured: boolean; }
export interface ModelSettings { activeProfileId: string; profileName: string; profiles: ModelProfile[]; provider: string; model: string; baseUrl: string; configured: boolean; providers: string[]; models: ModelOption[]; savedProfileId?: string; }

export function selectionLabel(selection?: MaterialSelection) {
  if (!selection) return '';
  return selection.startPage !== undefined
    ? `第 ${selection.startPage} 至 ${selection.endPage ?? selection.startPage} 页`
    : `第 ${selection.startParagraph} 至 ${selection.endParagraph ?? selection.startParagraph} 段`;
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const response = await fetch('/api' + path, {
    method: options.method || 'GET', signal: options.signal,
    headers: options.body === undefined ? undefined : { 'Content-Type': 'application/json', 'X-Co-Math-Request': '1' },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作未完成，请重试。');
  return result as T;
}

export function mergeMessages(previous: Message[], incoming: Message[]) {
  const result = new Map(previous.map(message => [message.id, message]));
  for (const message of incoming) {
    const old = result.get(message.id);
    if (old?.status && old.status !== 'running' && message.status === 'running') continue;
    if (old?.status === 'running' && message.status === 'running' && old.content.length > message.content.length) continue;
    result.set(message.id, message);
  }
  return [...result.values()].sort((a, b) => a.order - b.order);
}
