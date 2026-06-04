import { useState } from 'react';
import { CheckCircle2, ChevronUp, LoaderCircle, Pause, Play, Plus, RotateCcw, Settings, SlidersHorizontal } from 'lucide-react';
import clsx from 'clsx';
import SettingsModal from './SettingsModal';
import pptStudioIcon from '../../assets/ppt-studio-icon.png';
import { getJobTitle, getStatusLabel } from '../../utils/jobPresentation';
import { TASK_LAUNCH_CLOSE_LABEL, TASK_LAUNCH_CREATE_LABEL, TASK_LAUNCH_FROM_CURRENT_LABEL } from '../../utils/taskLaunchLabels';
import { getTaskLaunchSummaryText } from '../../utils/taskLaunchSummary';
import { getTopbarTaskAction } from '../../utils/topbarTaskAction';
import { useJobActions } from '../../hooks/useJobActions';

const ACTION_ICONS = {
  pause: Pause,
  play: Play,
  plus: Plus,
  check: CheckCircle2,
  loader: LoaderCircle,
};

const Header = ({
  currentJob,
  taskLaunchOpen,
  taskLaunchSourceJob,
  onCreateTask,
  onCreateTaskFromCurrent,
  onCloseTaskLaunch,
  onJobUpdated,
  onJobsRefresh,
}) => {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const { pendingKey, runAction } = useJobActions({
    currentJob,
    onJobUpdated,
  });
  const taskAction = getTopbarTaskAction(currentJob, pendingKey);
  const TaskActionIcon = ACTION_ICONS[taskAction.icon] || Plus;
  const hasCurrentJob = Boolean(currentJob?.job_id);
  const launchSummary = hasCurrentJob ? getTaskLaunchSummaryText(currentJob) : '填写内容、页数、风格与工作流';
  const configButtonLabel = taskLaunchOpen
    ? TASK_LAUNCH_CLOSE_LABEL
    : hasCurrentJob
      ? TASK_LAUNCH_FROM_CURRENT_LABEL
      : TASK_LAUNCH_CREATE_LABEL;
  const ConfigIcon = taskLaunchOpen ? ChevronUp : hasCurrentJob ? RotateCcw : SlidersHorizontal;

  const handleTaskAction = async () => {
    if (taskAction.disabled) return;
    if (taskAction.type === 'create') {
      onCreateTask?.();
      return;
    }

    const data = await runAction(taskAction.action, undefined, { key: taskAction.type || taskAction.action });
    if (data) {
      onJobsRefresh?.();
    }
  };

  return (
    <>
      <header className="app-topbar">
        <div className="brand-block">
          <div className="brand-mark">
            <img src={pptStudioIcon} alt="" />
          </div>
          <div>
            <h1>PPT 制作系统</h1>
            <p>任务中心 | 创作工作区 | PPT Studio</p>
          </div>
        </div>

        <div className="topbar-task">
          <span>当前任务</span>
          <strong>{currentJob ? getJobTitle(currentJob) : '准备创建新任务'}</strong>
          <em>{currentJob ? getStatusLabel(currentJob.status) : '未开始'}</em>
        </div>

        <div className="topbar-actions">
          <button
            type="button"
            className={clsx('topbar-config-drawer', taskLaunchOpen && 'is-open')}
            onClick={() => {
              if (taskLaunchOpen) {
                onCloseTaskLaunch?.();
              } else if (hasCurrentJob) {
                onCreateTaskFromCurrent?.();
              } else {
                onCreateTask?.();
              }
            }}
            aria-expanded={taskLaunchOpen}
          >
            <ConfigIcon size={17} />
            <span>
              <strong>{configButtonLabel}</strong>
              <small>{taskLaunchOpen && taskLaunchSourceJob ? getJobTitle(taskLaunchSourceJob) : launchSummary}</small>
            </span>
          </button>
          <button className="btn btn-secondary" onClick={() => setIsSettingsOpen(true)}>
            <Settings size={18} />
            <span>设置</span>
          </button>
          <button
            type="button"
            className={clsx('btn', taskAction.className)}
            onClick={handleTaskAction}
            disabled={taskAction.disabled}
          >
            <TaskActionIcon size={18} className={taskAction.icon === 'loader' ? 'spin' : undefined} />
            <span>{taskAction.label}</span>
          </button>
        </div>
      </header>
      
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </>
  );
};

export default Header;
