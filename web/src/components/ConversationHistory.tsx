import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { api, type Message } from '../api';
import { Markdown } from './Markdown';

export function ConversationHistory({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    void api<{ messages: Message[] }>(`/projects/${projectId}/chat`, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setMessages(data.messages);
    }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId]);
  return <section className="document-scroll history-view"><div className="reading-page">
    <header className="history-heading"><h1>历史讨论</h1><p>旧版网页保存的对话，仅供回看。coding agent 的会话请在原工具中查看。</p></header>
    {error && <p role="alert" className="error">{error}</p>}
    {loading ? <p role="status" className="muted">正在读取历史记录…</p> : !messages.length && !error ? <div className="document-empty"><History size={26}/><h3>没有网页历史讨论</h3><p>已保存的研究内容可以在左侧项目文件中阅读。</p></div> : messages.map(message => <article className={`message ${message.role}`} key={message.id}>
      <div className="message-meta"><strong>{message.role === 'user' ? '提问' : '模型草稿'}</strong><time>{new Date(message.createdAt).toLocaleString()}</time></div>
      {message.content && <Markdown>{message.content}</Markdown>}
      {message.status && message.status !== 'succeeded' && <p className="muted">此条回答在当时未完整结束。</p>}
      {!!message.sources?.length && <details className="sources"><summary>当时使用的材料</summary>{message.sources.map(path => <div key={path}>{path}</div>)}</details>}
    </article>)}
  </div></section>;
}
