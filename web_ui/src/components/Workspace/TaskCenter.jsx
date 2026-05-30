import { Archive, FileImage, FolderKanban, LayoutTemplate, PlusCircle } from 'lucide-react';
import clsx from 'clsx';
import SlideImage from './SlideImage';
import { formatTaskTime, getPageCount, getStatusLabel } from '../../utils/jobPresentation';

const RESOURCE_LINKS = [
  { key: 'materials', label: '素材库', description: '参考图、无文字元素图', icon: FileImage },
  { key: 'styles', label: '参考风格', description: '品牌色与风格图', icon: FolderKanban },
  { key: 'templates', label: '历史模板', description: '复用版式和导出结构', icon: LayoutTemplate },
];

const TaskCenter = ({ jobs, loading, currentJobId, onSelectJob, onCreateTask }) => {
  return (
    <aside className="workspace-panel task-center">
      <div className="workspace-panel__header">
        <span className="eyebrow">任务中心</span>
        <h2>围绕一份 PPT 持续协作</h2>
        <p>历史任务、项目素材和模板入口都放在这里，主舞台留给创作。</p>
      </div>

      <div className="task-center__body">
        <button type="button" className="new-task-button" onClick={onCreateTask}>
          <PlusCircle size={18} />
          <span>新建 PPT 任务</span>
        </button>

        <section className="task-section">
          <div className="section-title">
            <Archive size={15} />
            <span>历史任务</span>
          </div>
          <div className="task-list">
            {loading ? (
              <div className="empty-state">正在加载历史任务...</div>
            ) : jobs.length === 0 ? (
              <div className="empty-state">还没有任务，先从中间创建一份初稿。</div>
            ) : (
              jobs.map((job) => {
                const active = currentJobId === job.job_id;
                return (
                  <button
                    type="button"
                    key={job.job_id}
                    className={clsx('task-card', active && 'is-active')}
                    onClick={() => onSelectJob(job.job_id)}
                  >
                    <SlideImage
                      className="task-card__preview"
                      src={job.preview_image}
                      alt={job.title || '任务预览'}
                      variant="mini"
                      emptyTitle="P"
                    />
                    <span className="task-card__content">
                      <strong>{job.title || '未命名任务'}</strong>
                      <span>
                        {getStatusLabel(job.status)} · {getPageCount(job) || '-'} 页 · {formatTaskTime(job.updated_at)}
                      </span>
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="task-section task-section--resources">
          <div className="section-title">
            <FolderKanban size={15} />
            <span>素材与知识库</span>
          </div>
          <div className="resource-list">
            {RESOURCE_LINKS.map(({ key, label, description, icon: Icon }) => (
              <button type="button" className="resource-link" key={key}>
                <Icon size={17} />
                <span>
                  <strong>{label}</strong>
                  <small>{description}</small>
                </span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </aside>
  );
};

export default TaskCenter;
