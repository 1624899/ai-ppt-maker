const RESUMABLE_TASK_STATUSES = new Set(['interrupted', 'error']);

const normalizeStatus = (status) => String(status || '').trim();

export function getResumeControl(job) {
  const control = job?.resume_control && typeof job.resume_control === 'object'
    ? job.resume_control
    : {};
  const status = normalizeStatus(job?.status);
  const waitingForStop = Boolean(control.is_waiting_for_stop);
  const canResume = Boolean(control.can_resume) || (RESUMABLE_TASK_STATUSES.has(status) && !waitingForStop);
  const visible = waitingForStop || canResume || RESUMABLE_TASK_STATUSES.has(status);

  return {
    visible,
    canResume: Boolean(canResume && !waitingForStop),
    waitingForStop,
    label: String(control.label || (waitingForStop ? '停止收尾中' : '继续生成')),
    message: String(control.message || ''),
  };
}
