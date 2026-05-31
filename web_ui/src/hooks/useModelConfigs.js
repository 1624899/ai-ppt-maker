/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useState } from 'react';

const fetchJson = async (url, options) => {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.message || '请求失败');
  }
  return data;
};

export const useModelConfigs = (enabled = true) => {
  const [modelConfigs, setModelConfigs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    if (!enabled) return null;
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/model-configs');
      setModelConfigs(data);
      return data;
    } catch (err) {
      setError(err.message || '模型配置加载失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    if (enabled) {
      reload().catch(() => {});
    }
  }, [enabled, reload]);

  const saveModelConfig = useCallback(async ({ modelType, id, payload }) => {
    const url = id ? `/api/model-configs/${modelType}/${id}` : `/api/model-configs/${modelType}`;
    const method = id ? 'PUT' : 'POST';
    return fetchJson(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }, []);

  const activateModelConfig = useCallback(async ({ modelType, id }) => {
    return fetchJson(`/api/model-configs/${modelType}/${id}/active`, { method: 'POST' });
  }, []);

  const deleteModelConfig = useCallback(async ({ modelType, id }) => {
    return fetchJson(`/api/model-configs/${modelType}/${id}`, { method: 'DELETE' });
  }, []);

  const testModelConfig = useCallback(async ({ modelType, payload }) => {
    return fetchJson(`/api/model-configs/${modelType}/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }, []);

  return {
    modelConfigs,
    loading,
    error,
    reload,
    saveModelConfig,
    activateModelConfig,
    deleteModelConfig,
    testModelConfig,
  };
};
