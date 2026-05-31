import { useCallback, useEffect, useState } from 'react';

const fetchJobItems = async () => {
  const res = await fetch('/api/jobs');
  if (!res.ok) throw new Error(`获取任务列表失败：${res.status}`);
  const data = await res.json();
  return data.items || [];
};

export const useJobs = () => {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  const refreshJobs = useCallback(async () => {
    const items = await fetchJobItems();
    setJobs(items);
    setLoading(false);
    return items;
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadInitialJobs = async () => {
      try {
        const items = await fetchJobItems();
        if (cancelled) return;
        setJobs(items);
      } catch (err) {
        if (!cancelled) {
          console.error(err);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadInitialJobs();

    const source = new EventSource('/api/jobs/stream');
    source.addEventListener('history', (event) => {
      try {
        const data = JSON.parse(event.data);
        if (!cancelled) {
          setJobs(data.items || []);
          setLoading(false);
        }
      } catch (e) {
        console.error(e);
      }
    });

    return () => {
      cancelled = true;
      source.close();
    };
  }, []);

  return { jobs, loading, setJobs, refreshJobs };
};
