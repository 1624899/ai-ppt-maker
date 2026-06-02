const RUNNING_TASK_STATUSES = new Set(['queued', 'running', 'stopping']);
const RESUMABLE_TASK_STATUSES = new Set(['interrupted', 'error']);

const normalizeStatus = (status) => String(status || '').trim();

export function getTopbarTaskAction(job, pendingKey = '') {
  const status = normalizeStatus(job?.status);

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

  if (RESUMABLE_TASK_STATUSES.has(status)) {
    const pending = pendingKey === 'resume';
    return {
      type: 'resume',
      action: 'resume',
      icon: 'play',
      label: pending ? '继续中...' : '继续任务',
      className: 'btn-task-resume',
      disabled: pending,
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
