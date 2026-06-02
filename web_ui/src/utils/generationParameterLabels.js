import { getWorkflowModeLabel } from './workflowMode';

const JOB_TARGET_LABELS = {
  editable_ppt: '可编辑 PPT',
  reference_only: '图片版 PPT',
};

const IMAGE_QUALITY_LABELS = {
  auto: 'Auto',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
};

const RICHNESS_LABELS = {
  low: '低',
  medium: '中',
  high: '高',
};

const STYLE_ADHERENCE_LABELS = {
  loose: '宽松',
  balanced: '适度',
  strict: '严格',
};

const normalizeText = (value) => String(value || '').trim();

export function getJobTargetLabel(value) {
  const key = normalizeText(value);
  return JOB_TARGET_LABELS[key] || key;
}

export function getImageQualityLabel(value) {
  const key = normalizeText(value);
  return IMAGE_QUALITY_LABELS[key] || key;
}

export function getRichnessLabel(value) {
  const key = normalizeText(value);
  return RICHNESS_LABELS[key] || key;
}

export function getStyleAdherenceLabel(value) {
  const key = normalizeText(value);
  return STYLE_ADHERENCE_LABELS[key] || key;
}

export function getGenerationParameterLabel(name, value) {
  if (name === 'workflowMode') return getWorkflowModeLabel(value);
  if (name === 'jobTarget') return getJobTargetLabel(value);
  if (name === 'imageQuality') return getImageQualityLabel(value);
  if (name === 'pageRichnessDefault') return getRichnessLabel(value);
  if (name === 'referenceStyleAdherence') return getStyleAdherenceLabel(value);
  return normalizeText(value);
}
