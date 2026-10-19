import { ListChecks } from 'lucide-react';
import type { Document } from '../api';
import { Markdown } from './Markdown';
import { MathText } from './MathText';

const labels: Record<string, string> = {
  onboarding: '讨论中', draft: '草稿', proposed: '待确认', approved: '已确认',
  active: '进行中', in_progress: '进行中', complete: '已记录完成', completed: '已记录完成',
  blocked: '待处理', pending: '待确认', cancelled: '已取消', archived: '已归档',
};
const statusLabel = (status: string) => Object.hasOwn(labels, status) ? labels[status] : '';

export function GoalsView({ document }: { document: Document }) {
  const view = document.goalsView;
  const language = view?.language === 'English' ? '英文' : view?.language || '待选择';
  return <section className="goals-view">
    <header className="goals-view-header"><div><h1>研究目标</h1><p>记录希望解决的问题，以及具体要达成的结果。</p></div>{view && <span className="goal-language">文档语言 · {language}</span>}</header>
    {view && <>
      <section className="research-question"><div className="goal-section-heading"><h2>研究问题</h2>{statusLabel(view.questionStatus) && <span>{statusLabel(view.questionStatus)}</span>}</div>
        {view.question ? <Markdown>{view.question}</Markdown> : <p className="muted">暂未填写研究问题，可以先在 coding agent 中描述你的想法。</p>}
      </section>
      <section className="research-goals"><div className="goal-section-heading"><h2>具体目标</h2><span>{view.goals.length} 项</span></div>
        {view.goals.length ? view.goals.map((goal, index) => <article className="research-goal" key={`${goal.id}-${index}`}><header><span className="goal-number">{String(index + 1).padStart(2, '0')}</span><h3><MathText inline>{goal.title}</MathText></h3><span className="goal-status">{statusLabel(goal.status) || '状态待说明'}</span></header>{goal.details.map((detail, position) => <div className="goal-detail" key={position}><h4>{detail.label}</h4><Markdown>{detail.content}</Markdown></div>)}</article>) :
          <div className="goals-empty"><ListChecks size={25}/><div><h3>还没有单独列出的目标</h3><p>在 coding agent 中讨论并确认目标后，这里会显示保存的记录。</p></div></div>}
      </section>
    </>}
    <details className="goals-source"><summary>查看原始配置</summary><p>{document.path}</p><pre className="source-document">{document.rawContent ?? document.content}</pre></details>
  </section>;
}
