import { useEffect, useId, useRef, useState } from 'react';
import { ArrowUp, Square, BookmarkPlus, Copy, MessageCircle, X, Check, Settings, ChevronDown, BookOpen } from 'lucide-react';
import { selectionLabel, type Message, type ModelSettings, type Skill, type MaterialSelection } from '../api';
import { Markdown } from './Markdown';
import { skillTitle } from '../skill-labels';

const states: Record<string, string> = { running: '正在思考与生成', succeeded: '回答已保存', failed: '请求失败', cancelled: '已停止', interrupted: '运行中断' };

export function Chat({ messages, settings, files, ranges = {}, busy, sending, switchingModel, connected, onSend, onStop, onSave, onRemoveFile, onSettings, onSelectModel, selectedSkill, onSkills, onClearSkill }: {
  messages: Message[]; settings: ModelSettings | null; files: string[]; busy: boolean; sending: boolean; connected: boolean;
  ranges?: Record<string, MaterialSelection>;
  onSend: (content: string) => Promise<void>; onStop: () => void; onSave: (content: string) => void; onRemoveFile: (path: string) => void; onSettings: () => void;
  switchingModel: boolean; onSelectModel: (profileId: string, model?: string) => Promise<void>;
  selectedSkill: Skill | null; onSkills: () => void; onClearSkill: () => void;
}) {
  const [input, setInput] = useState(''); const [copied, setCopied] = useState('');
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const picker = useRef<HTMLDivElement>(null); const pickerButton = useRef<HTMLButtonElement>(null);
  const pickerId = useId();
  const scroll = useRef<HTMLDivElement>(null); const follow = useRef(true);
  useEffect(() => { if (follow.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight; }, [messages]);
  useEffect(() => {
    if (!modelPickerOpen) return;
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !picker.current?.contains(event.target)) setModelPickerOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape') { setModelPickerOpen(false); pickerButton.current?.focus(); }
    }
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [modelPickerOpen]);
  function manageModels() { setModelPickerOpen(false); onSettings(); }
  async function submit() {
    if (!input.trim() || busy || sending) return;
    const submitted = input;
    try { await onSend(submitted); setInput(current => current === submitted ? '' : current); follow.current = true; } catch { /* Parent shows the error. */ }
  }
  return <aside className="chat-pane" id="research-chat">
    <header className="chat-header">
      <div className="chat-heading"><MessageCircle size={17}/><strong>研究对话</strong>{!connected && <span className="connection-dot" title="正在连接本地服务"/>}</div>
      <div className="chat-header-tools" ref={picker} onBlur={event => { if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget)) setModelPickerOpen(false); }}>
        <button ref={pickerButton} className={'chat-model-toggle ' + (modelPickerOpen ? 'open' : '')} aria-label="切换服务和模型" aria-expanded={modelPickerOpen} aria-controls={pickerId} title={`${settings?.profileName || '模型服务'} · ${settings?.model || '未选择模型'}`} onClick={() => setModelPickerOpen(open => !open)}>
          <span>{switchingModel ? '切换中…' : settings?.model || '选择模型'}</span><ChevronDown size={13}/>
        </button>
        {modelPickerOpen && <div className="chat-model-popover" id={pickerId} role="group" aria-label="服务和模型选项">
          <div className="model-popover-heading"><span>模型</span><button onClick={manageModels} aria-label="管理 API 配置"><Settings size={13}/>管理服务</button></div>
          <label>服务<select aria-label="模型服务配置" value={settings?.activeProfileId || ''} disabled={switchingModel || !settings?.profiles.length} onChange={e => void onSelectModel(e.target.value)}>{!settings?.profiles.length && <option value="">尚无服务配置</option>}{settings?.profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}{profile.configured ? '' : ' · 未填密钥'}</option>)}</select></label>
          <label>模型<select aria-label="当前模型" value={settings?.model || ''} disabled={switchingModel || !settings?.models.length} onChange={e => { if (settings) { void onSelectModel(settings.activeProfileId, e.target.value); setModelPickerOpen(false); pickerButton.current?.focus(); } }}>{!settings?.model && <option value="">请先配置模型</option>}{settings?.models.map(model => <option key={model.id} value={model.id}>{model.id}</option>)}</select></label>
          {!settings?.configured && <button className="model-key-prompt" onClick={manageModels}>填写 API 密钥</button>}
        </div>}
      </div>
    </header>
    <div className="messages" ref={scroll} onScroll={() => { const e = scroll.current; if (e) follow.current = e.scrollHeight - e.scrollTop - e.clientHeight < 100; }}>
      {!messages.length && <div className="chat-empty"><span className="empty-symbol">∴</span><h3>从一个问题开始</h3><p>梳理假设，推导一个结论，<br/>或一起找出证明中缺少的一步。</p><button onClick={() => setInput('请根据项目问题，梳理已知条件、研究目标和下一步需要澄清的问题。')}>帮我梳理这个问题 <ArrowUp size={14}/></button><button onClick={() => setInput('请阅读所选材料，指出关键假设、推导中尚未说明的步骤，以及值得核查的边界情况。')}>检查材料中的推导 <ArrowUp size={14}/></button></div>}
      {messages.map(message => <article className={'message ' + message.role} key={message.id}>
        <div className="message-meta"><strong>{message.role === 'user' ? '你' : 'Co-Math'}</strong><span>{message.role === 'assistant' ? states[message.status || ''] : new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></div>
        {message.role === 'assistant' && message.model && <div className="message-model">{message.profileName ? `${message.profileName} · ` : ''}{message.model}</div>}
        {message.skill && <details className="used-skill"><summary>Skill · {skillTitle(message.skill)} · 流程指导</summary><p>{message.skill.source === 'verymath' ? 'VeryMath' : '项目'} / {message.skill.path}</p>{message.skill.resources?.map(path => <p key={path}>已加载：{path}</p>)}{message.skill.warnings?.map((warning, index) => <p key={index}>{warning}</p>)}</details>}
        {message.content ? <Markdown>{message.content}</Markdown> : message.status === 'running' ? <div className="thinking"><i/><i/><i/></div> : null}
        {message.error && <p role="status" className="error">{message.error}</p>}
        {!!message.sources?.length && <details className="sources"><summary>使用了 {message.sources.length} 份项目材料{message.sourceNotes?.some(note => note.includes('节选')) ? ' · 含节选' : ''}</summary>{message.sources.map(path => <div key={path}>{path}</div>)}{message.sourceNotes?.map((note, index) => <p key={index}>{note}</p>)}</details>}
        {message.role === 'assistant' && message.content && message.status !== 'running' && <div className="message-actions"><button onClick={() => onSave(`模型：${message.profileName ? message.profileName + ' / ' : ''}${message.model || '未知'} · ${new Date(message.createdAt).toLocaleString()}\n\n状态：研究草稿，未经独立审稿或形式化验证。\n\n${message.content}`)}><BookmarkPlus size={14}/>保存为笔记</button><button aria-label="复制回答" onClick={async () => { try { await navigator.clipboard.writeText(message.content); setCopied(message.id); } catch { setCopied(''); } }}>{copied === message.id ? <Check size={14}/> : <Copy size={14}/>}</button></div>}
      </article>)}
    </div>
    <div className="composer-area">
      {selectedSkill && <div className="selected-skill"><button onClick={onSkills}><BookOpen size={13}/>{skillTitle(selectedSkill)}</button><button aria-label="取消使用 Skill" onClick={onClearSkill}><X size={12}/></button></div>}
      {!!files.length && <div className="attachments">{files.map(path => <span key={path} title={path}>{path.split('/').at(-1)}{ranges[path] ? ` · ${selectionLabel(ranges[path])}` : ''}<button aria-label={`移除材料 ${path}`} onClick={() => onRemoveFile(path)}><X size={12}/></button></span>)}</div>}
      <div className="composer"><textarea aria-label="研究问题" placeholder={settings?.configured ? '提出问题，或继续这段推导…' : '先配置模型，即可围绕项目讨论…'} value={input} maxLength={20000} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void submit(); } }}/><div className="composer-footer"><div className="composer-tools"><button onClick={onSkills} aria-label="选择 VeryMath Skill"><BookOpen size={14}/>Skill</button><span>⌘ / Ctrl + Enter</span></div>{busy ? <button className="stop" onClick={onStop}><Square size={12} fill="currentColor"/>停止</button> : <button className="send" aria-label="发送问题" disabled={!input.trim() || sending || !settings?.configured} onClick={() => void submit()}><ArrowUp size={19}/></button>}</div></div>
      <p className="context-note">发送项目概况、所选材料范围及最近对话；超出容量时仍会节选。<br/>模型回答需要核查，可保存为研究笔记。</p>
    </div>
  </aside>;
}
