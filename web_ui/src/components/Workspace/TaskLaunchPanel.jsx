import { useCallback, useState } from 'react';
import { ClipboardList, Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';
import CreationForm from './CreationForm';
import { buildTaskLaunchSummary } from '../../utils/taskLaunchSummary';
import { buildTaskLaunchInsights } from '../../utils/taskLaunchInsights';
import { TASK_LAUNCH_FROM_CURRENT_LABEL } from '../../utils/taskLaunchLabels';
import { getJobTitle } from '../../utils/jobPresentation';

const TaskLaunchPanel = ({
  sourceJob,
  workflowMode,
  onWorkflowModeChange,
  onCreated,
  onClose,
}) => {
  const isFromCurrentJob = Boolean(sourceJob?.job_id);
  const [launchParams, setLaunchParams] = useState(null);
  const summaryItems = buildTaskLaunchSummary(sourceJob);
  const insightItems = buildTaskLaunchInsights(launchParams || {}, { limit: 4 });
  const title = isFromCurrentJob ? TASK_LAUNCH_FROM_CURRENT_LABEL : '创建 PPT 任务';
  const description = isFromCurrentJob
    ? '旧任务会被保留，新任务会复用当前内容、页数、风格与生成设置。'
    : '先定义任务边界，提交后启动配置会自动收起，工作区进入执行流。';
  const handleParamsChange = useCallback((params) => {
    setLaunchParams(params);
  }, []);

  return (
    <motion.main
      className="workspace-panel task-launch-panel"
      aria-label={title}
      initial={{ opacity: 0, y: -18, scale: 0.985 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -26, scale: 0.96 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      style={{ transformOrigin: 'top center' }}
    >
      <header className="workspace-panel__header task-launch-panel__head">
        <div className="task-launch-panel__title">
          <span className="eyebrow">任务 Brief</span>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <button className="btn btn-secondary" type="button" onClick={onClose}>
          收起到顶栏
        </button>
      </header>

      <div className="task-launch-panel__body">
        <aside className="task-launch-brief">
          {!isFromCurrentJob && (
            <div className="task-launch-brief__icon">
              <ClipboardList size={24} />
            </div>
          )}
          <span>{isFromCurrentJob ? '新建分支' : '启动配置'}</span>
          <h3>{isFromCurrentJob ? getJobTitle(sourceJob) : '把生成参数放在任务边界里'}</h3>
          <p>
            {isFromCurrentJob
              ? '如果当前结果不满意，可以从同一组参数出发生成一个新分支，方便对比和回退。'
              : '对话负责改意图，规划负责改结构，编辑负责改单页；这里只负责定义新任务如何启动。'}
          </p>
          {insightItems.length > 0 && (
            <div className="task-launch-insights" aria-label="参数解读">
              <strong>参数解读</strong>
              {insightItems.map((item) => (
                <article key={item.label}>
                  <span>{item.label}</span>
                  <em>{item.value}</em>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          )}
          {summaryItems.length > 0 && (
            <div className="task-launch-summary" aria-label="当前任务参数摘要">
              <strong>当前任务参数</strong>
              <div className="task-launch-brief__chips">
                {summaryItems.map((item) => <em key={item}>{item}</em>)}
              </div>
            </div>
          )}
          <div className="task-launch-brief__note">
            <Sparkles size={16} />
            <small>任务提交后会像抽屉一样收起，参数仍会随任务保留在顶栏入口里。</small>
          </div>
        </aside>

        <section className="task-launch-form-card">
          <CreationForm
            compact
            currentJob={sourceJob}
            workflowMode={workflowMode}
            onWorkflowModeChange={onWorkflowModeChange}
            onCreated={onCreated}
            onParamsChange={handleParamsChange}
            submitLabel={isFromCurrentJob ? TASK_LAUNCH_FROM_CURRENT_LABEL : undefined}
          />
        </section>
      </div>
    </motion.main>
  );
};

export default TaskLaunchPanel;
