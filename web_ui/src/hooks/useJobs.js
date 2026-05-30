import { useState, useEffect } from 'react';

export const useJobs = () => {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/jobs')
      .then(res => res.json())
      .then(data => {
        setJobs(data.items || []);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });

    const source = new EventSource('/api/jobs/stream');
    source.addEventListener('history', (event) => {
      try {
        const data = JSON.parse(event.data);
        setJobs(data.items || []);
      } catch (e) {
        console.error(e);
      }
    });

    return () => source.close();
  }, []);

  return { jobs, loading };
};
