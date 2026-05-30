const parseJsonResponse = async (response) => {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败：${response.status}`);
  }
  return payload;
};

export const postJobAction = async (jobId, action, payload) => {
  const response = await fetch(`/api/jobs/${jobId}/${action}`, {
    method: 'POST',
    headers: payload ? { 'Content-Type': 'application/json' } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  return parseJsonResponse(response);
};

export const postJobOperation = async (jobId, operation) => {
  const response = await fetch(`/api/jobs/${jobId}/operations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(operation),
  });
  return parseJsonResponse(response);
};

export const postAgentDraft = async (jobId, payload) => {
  const response = await fetch(`/api/jobs/${jobId}/agent/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse(response);
};

export const clearAgentConversation = async (jobId) => {
  const response = await fetch(`/api/jobs/${jobId}/agent/conversation`, {
    method: 'DELETE',
  });
  return parseJsonResponse(response);
};
