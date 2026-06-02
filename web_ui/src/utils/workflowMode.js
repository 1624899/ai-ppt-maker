export const WORKFLOW_MODE_AUTO = 'auto';
export const WORKFLOW_MODE_GUIDED = 'guided';

export const WORKFLOW_MODE_OPTIONS = [
  {
    value: WORKFLOW_MODE_AUTO,
    label: '一键生成',
    description: '直接跑完整生成链路',
    submitLabel: '开始生成',
  },
  {
    value: WORKFLOW_MODE_GUIDED,
    label: '分步规划',
    description: '先生成规划，确认后继续',
    submitLabel: '生成规划',
  },
];

export function normalizeWorkflowMode(value) {
  const text = String(value || '').trim();
  return WORKFLOW_MODE_OPTIONS.some((option) => option.value === text) ? text : WORKFLOW_MODE_AUTO;
}

export function getWorkflowModeOption(value) {
  const normalized = normalizeWorkflowMode(value);
  return WORKFLOW_MODE_OPTIONS.find((option) => option.value === normalized) || WORKFLOW_MODE_OPTIONS[0];
}

export function getWorkflowModeFromJob(job) {
  return normalizeWorkflowMode(job?.job_meta?.workflow_mode || job?.workflow_mode);
}

export function getWorkflowModeLabel(value) {
  return getWorkflowModeOption(value).label;
}

export function getWorkflowSubmitLabel(value, fallback = '生成初稿') {
  return getWorkflowModeOption(value).submitLabel || fallback;
}

export function isAwaitingPlanConfirmation(job) {
  return String(job?.status || '').trim() === 'awaiting_plan_confirmation';
}
