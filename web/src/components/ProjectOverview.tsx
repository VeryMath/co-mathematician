import type { Project } from '../api';
import { MathText } from './MathText';

const reviewLabels = {
  reviewed: '报告审查通过',
  pending: '报告待核查',
  blocked: '审查记录待处理',
};

export function ProjectOverview({ project, workspace, onOpen }: {
  project: Project;
  workspace: string;
  onOpen: (path: string) => void;
}) {
  const entries = [
    { title: '工作论文', path: project.working_paper },
    { title: '论文提纲', path: project.paper_outline },
    { title: '最近笔记', path: project.latest_note },
  ].filter((item): item is { title: string; path: string } => Boolean(item.path));
  return <div className="document-scroll">
    <section className="reading-page project-overview" aria-labelledby="overview-heading">
      <h1 id="overview-heading">研究概览</h1>
      <section className="overview-question">
        <h2>研究问题</h2>
        <MathText>{project.question || '等待记录研究问题。'}</MathText>
      </section>
      <dl className="overview-progress">
        <div><dt>最近进展</dt><dd><MathText>{project.recent_update || '暂无进展记录。'}</MathText></dd></div>
        <div><dt>未解决问题</dt><dd><MathText>{project.open_question || '暂无问题记录。'}</MathText></dd></div>
        {project.blocker && <div><dt>需要处理</dt><dd>{project.blocker}</dd></div>}
        <div><dt>下一步</dt><dd><MathText>{project.next_action || '在 coding agent 中查看项目说明。'}</MathText></dd></div>
      </dl>
      <section className="overview-reports">
        <h2>报告与成果</h2>
        {project.reports.length || entries.length ? <ul>
          {project.reports.map(report => <li key={report.path}>
            <button type="button" className="project-file-link" onClick={() => onOpen(report.path)}><MathText inline>{report.title}</MathText></button>
            <span>{reviewLabels[report.review_status]}</span>
            {report.reviews.length > 0 && <details className="overview-reviews">
              <summary>审查记录</summary>
              {report.reviews.map(path => <button key={path} type="button" className="project-file-link"
                onClick={() => onOpen(path)}>{path.split('/').at(-1)}</button>)}
            </details>}
          </li>)}
          {entries.map(item => <li key={item.path}>
            <button type="button" className="project-file-link" onClick={() => onOpen(item.path)}>{item.title}</button>
          </li>)}
        </ul> : <p>已保存的报告、论文和笔记会显示在这里。</p>}
      </section>
      <button type="button" className="project-file-link" onClick={() => onOpen(workspace + '/project/PROJECT_STATUS.md')}>查看完整进展记录</button>
    </section>
  </div>;
}
