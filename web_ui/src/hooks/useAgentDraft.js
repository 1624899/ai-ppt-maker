import { useState } from 'react';
import { postAgentDraft } from '../utils/jobActions';

export const useAgentDraft = ({ currentJob } = {}) => {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const jobId = currentJob?.job_id;

  const createDraft = async (payload) => {
    if (!jobId) return null;
    setPending(true);
    setError('');
    try {
      return await postAgentDraft(jobId, payload);
    } catch (err) {
      const message = err.message || 'Agent 理解失败';
      setError(message);
      return null;
    } finally {
      setPending(false);
    }
  };

  return {
    pending,
    error,
    setError,
    createDraft,
  };
};
