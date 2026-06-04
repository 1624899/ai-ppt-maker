import { getResumeControl } from './resumeControl';

const RUNNING_TASK_STATUSES = new Set(['queued', 'running', 'stopping']);

const normalizeStatus = (status) => String(status || '').trim();

export function getTopbarTaskAction(job, pendingKey = '') {
  const status = normalizeStatus(job?.status);
  const resumeControl = getResumeControl(job);

  if (status === 'awaiting_plan_confirmation') {
    const pending = pendingKey === 'confirm-plan';
    return {
      type: 'confirm-plan',
      action: 'plan/confirm',
      icon: 'check',
      label: pending ? '确认中...' : '确认规划',
      className: 'btn-task-resume',
      disabled: pending,
    };
  }

  if (resumeControl.visible) {
    const pending = pendingKey === 'resume';
    const waiting = resumeControl.waitingForStop;
    return {
      type: 'resume',
      action: 'resume',
      icon: waiting ? 'loader' : 'play',
      label: pending ? '提交中...' : waiting ? resumeControl.label : '继续任务',
      className: waiting ? 'btn-task-waiting' : 'btn-task-resume',
      disabled: pending || !resumeControl.canResume,
    };
  }

  if (RUNNING_TASK_STATUSES.has(status)) {
    const pending = pendingKey === 'interrupt' || status === 'stopping';
    return {
      type: 'pause',
      action: 'interrupt',
      icon: 'pause',
      label: pending ? '暂停中...' : '暂停任务',
      className: 'btn-task-pause',
      disabled: pending,
    };
  }

  return {
    type: 'create',
    action: '',
    icon: 'plus',
    label: '创建任务',
    className: 'btn-primary',
    disabled: false,
  };
}
