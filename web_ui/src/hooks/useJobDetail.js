import { useEffect, useState } from 'react';

export const useJobDetail = (jobId) => {
  const [job, setJob] = useState(null);
  const [errorState, setErrorState] = useState(null);
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
          setJob(data);
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
        if (!cancelled) setJob(data);
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
  }, [jobId]);

  const loading = Boolean(jobId && !visibleJob && !visibleError);
  return { job: visibleJob, loading, error: visibleError, setJob };
};
