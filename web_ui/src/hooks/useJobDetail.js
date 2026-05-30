import { useEffect, useState } from 'react';

export const useJobDetail = (jobId) => {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

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
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });

    const source = new EventSource(`/api/jobs/${jobId}/stream`);
    source.addEventListener('job', (event) => {
      try {
        const data = JSON.parse(event.data);
        if (!cancelled) setJob(data);
      } catch (err) {
        if (!cancelled) setError(err);
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

  const loading = Boolean(jobId && (!job || job.job_id !== jobId) && !error);
  return { job, loading, error, setJob };
};
