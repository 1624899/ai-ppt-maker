import { useState } from 'react';
import { postJobAction, postJobOperation } from '../utils/jobActions';

export const useJobActions = ({ currentJob, onJobUpdated } = {}) => {
  const [pendingKey, setPendingKey] = useState('');
  const [error, setError] = useState('');
  const jobId = currentJob?.job_id;

  const runAction = async (action, payload, options = {}) => {
    if (!jobId) return null;
    const key = options.key || action;
    setPendingKey(key);
    setError('');
    try {
      const data = await postJobAction(jobId, action, payload);
      onJobUpdated?.(data);
      return data;
    } catch (err) {
      const message = err.message || '操作失败';
      setError(message);
      options.onError?.(message);
      return null;
    } finally {
      setPendingKey((value) => (value === key ? '' : value));
    }
  };

  const runOperation = async (operation, options = {}) => {
    if (!jobId) return null;
    const key = options.key || operation.operation_type || operation.type || 'operation';
    setPendingKey(key);
    setError('');
    try {
      const data = await postJobOperation(jobId, operation);
      onJobUpdated?.(data);
      return data;
    } catch (err) {
      const message = err.message || '操作失败';
      setError(message);
      options.onError?.(message);
      return null;
    } finally {
      setPendingKey((value) => (value === key ? '' : value));
    }
  };

  return {
    pendingKey,
    error,
    setError,
    runAction,
    runOperation,
  };
};
