import { useEffect, useRef, useState } from 'react';
import { mergeJobState } from '../utils/jobStateMerge';

const STREAM_RESTART_FROM_STATUSES = new Set(['completed', 'error', 'interrupted']);
const ACTIVE_STREAM_STATUSES = new Set(['queued', 'running', 'stopping']);

const normalizeStatus = (status) => String(status || '').trim();

export const useJobDetail = (jobId) => {
  const [job, setJob] = useState(null);
  const [errorState, setErrorState] = useState(null);
  const [streamRevision, setStreamRevision] = useState(0);
  const previousStreamStatusRef = useRef({ jobId: '', status: '' });
  const visibleJob = jobId && job?.job_id === jobId ? job : null;
  const visibleError = errorState?.jobId === jobId ? errorState.error : null;

  useEffect(() => {
    if (!jobId) {
      return undefined;
    }

    let cancelled = false;

    fetch(`/api/jobs/${jobId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`获取任务失败：${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) {
          setJob((current) => mergeJobState(current, data));
          setErrorState(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setErrorState({ jobId, error: err });
      });

    const source = new EventSource(`/api/jobs/${jobId}/stream`);
    source.addEventListener('job', (event) => {
      try {
        const data = JSON.parse(event.data);
        if (!cancelled) setJob((current) => mergeJobState(current, data));
      } catch (err) {
        if (!cancelled) setErrorState({ jobId, error: err });
      }
    });
    source.addEventListener('error', () => {
      source.close();
    });

    return () => {
      cancelled = true;
      source.close();
    };
  }, [jobId, streamRevision]);

  useEffect(() => {
    if (!jobId || visibleJob?.job_id !== jobId) return undefined;
    const status = normalizeStatus(visibleJob?.status);
    const previous = previousStreamStatusRef.current;
    previousStreamStatusRef.current = { jobId, status };

    if (
      previous.jobId === jobId
      && STREAM_RESTART_FROM_STATUSES.has(previous.status)
      && ACTIVE_STREAM_STATUSES.has(status)
    ) {
      setStreamRevision((value) => value + 1);
    }
    return undefined;
  }, [jobId, visibleJob?.job_id, visibleJob?.status]);

  const loading = Boolean(jobId && !visibleJob && !visibleError);
  return { job: visibleJob, loading, error: visibleError, setJob };
};
