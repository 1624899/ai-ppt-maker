const STATUS_LABELS = {
  queued: '等待执行',
  pending: '等待中',
  running: '生成中',
  stopping: '停止中',
  awaiting_plan_confirmation: '等待确认规划',
  awaiting_reference_confirmation: '等待确认原稿图',
  interrupted: '已中断',
  completed: '已完成',
  error: '生成失败'
};

export const getJobProgress = (job) => {
  const status = String(job?.status || '').trim();
  const stages = Array.isArray(job?.stages) ? job.stages : [];
  const completed = stages.filter((stage) => ['completed', 'skipped'].includes(stage?.status)).length;
  const percent = status === 'completed'
    ? 100
    : stages.length > 0
      ? Math.min(99, Math.round((completed / stages.length) * 100))
      : 0;
  const currentStage = stages.find((stage) => stage?.key === job?.current_stage)
    || stages.find((stage) => ['running', 'queued', 'pending'].includes(stage?.status));

  return {
    percent,
    statusLabel: STATUS_LABELS[status] || status || '未知状态',
    stageLabel: String(currentStage?.label || currentStage?.summary || '').trim()
  };
};

export const isJobActive = (job) => ['queued', 'pending', 'running', 'stopping'].includes(String(job?.status || '').trim());
