import { useEffect, useMemo, useState } from 'react';
import { mergeJobState } from '../utils/jobStateMerge';
import { isActiveJobStatus, shouldOpenJobDetailStream } from '../utils/jobDetailStream';

export const useJobDetail = (jobId) => {
  const [job, setJob] = useState(null);
  const [errorState, setErrorState] = useState(null);
  const [streamRevision, setStreamRevision] = useState(0);
  const visibleJob = jobId && job?.job_id === jobId ? job : null;
  const visibleError = errorState?.jobId === jobId ? errorState.error : null;
  const shouldStream = useMemo(() => {
    return shouldOpenJobDetailStream(jobId, visibleJob);
  }, [jobId, visibleJob?.job_id, visibleJob?.status]);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setErrorState(null);
      return undefined;
    }

    let cancelled = false;
    const controller = new AbortController();

    fetch(`/api/jobs/${jobId}`, { signal: controller.signal })
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
        if (err?.name === 'AbortError') return;
        if (!cancelled) setErrorState({ jobId, error: err });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !shouldStream) {
      return undefined;
    }

    let cancelled = false;
    let closedAfterTerminalState = false;
    let reconnectTimer = null;

    // 历史任务只走普通详情请求，运行中任务才保持实时流，避免快速切换时堆积 SSE 连接。
    const source = new EventSource(`/api/jobs/${jobId}/stream`);
    source.addEventListener('job', (event) => {
      try {
        const data = JSON.parse(event.data);
        if (!cancelled) {
          setJob((current) => mergeJobState(current, data));
          if (!isActiveJobStatus(data?.status)) {
            closedAfterTerminalState = true;
            source.close();
          }
        }
      } catch (err) {
        if (!cancelled) setErrorState({ jobId, error: err });
      }
    });
    source.addEventListener('error', () => {
      source.close();
      if (!cancelled && !closedAfterTerminalState) {
        reconnectTimer = setTimeout(() => {
          setStreamRevision((value) => value + 1);
        }, 1200);
      }
    });

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      source.close();
    };
  }, [jobId, shouldStream, streamRevision]);

  const loading = Boolean(jobId && !visibleJob && !visibleError);
  return { job: visibleJob, loading, error: visibleError, setJob };
};
