const ACTIVE_STREAM_STATUSES = new Set(['queued', 'running', 'stopping']);

export const normalizeJobStatus = (status) => String(status || '').trim();

const isWaitingForStop = (job) => (
  Boolean(
    job?.resume_control
    && typeof job.resume_control === 'object'
    && job.resume_control.is_waiting_for_stop
  )
);

export const shouldKeepJobDetailStream = (job) => (
  ACTIVE_STREAM_STATUSES.has(normalizeJobStatus(job?.status)) || isWaitingForStop(job)
);

export const shouldOpenJobDetailStream = (jobId, job) => (
  Boolean(jobId && job?.job_id === jobId && shouldKeepJobDetailStream(job))
);

export const isActiveJobStatus = (status) => ACTIVE_STREAM_STATUSES.has(normalizeJobStatus(status));
