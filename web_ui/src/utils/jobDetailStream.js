const ACTIVE_STREAM_STATUSES = new Set(['queued', 'running', 'stopping']);

export const normalizeJobStatus = (status) => String(status || '').trim();

export const shouldOpenJobDetailStream = (jobId, job) => (
  Boolean(jobId && job?.job_id === jobId && ACTIVE_STREAM_STATUSES.has(normalizeJobStatus(job?.status)))
);

export const isActiveJobStatus = (status) => ACTIVE_STREAM_STATUSES.has(normalizeJobStatus(status));
