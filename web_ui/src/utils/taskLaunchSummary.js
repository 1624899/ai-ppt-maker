import { getJobMeta, getPageCount, getStyleReferenceImages } from './jobPresentation';
import { getGenerationParameterLabel, getJobTargetLabel } from './generationParameterLabels';
import { getWorkflowModeLabel } from './workflowMode';

const normalizeText = (value) => String(value || '').trim();

const pushUnique = (items, value) => {
  const text = normalizeText(value);
  if (text && !items.includes(text)) items.push(text);
};

export function buildTaskLaunchSummary(job, { compact = false } = {}) {
  if (!job) return [];

  const meta = getJobMeta(job);
  const generationOptions = meta.generation_options || {};
  const items = [];
  const pageCount = Number(meta.page_count || job.page_count || getPageCount(job) || 0);
  const workflowMode = meta.workflow_mode || job.workflow_mode;
  const jobTarget = normalizeText(meta.job_target || job.job_target);
  const sourceModeLabel = normalizeText(meta.source_mode_label || job.source_mode_label);
  const imagePreset = meta.image_preset || {};
  const imagePresetLabel = normalizeText(imagePreset.label || imagePreset.name || job.image_preset);
  const imageQuality = normalizeText(meta.image_quality || job.image_quality);
  const styleReferenceCount = getStyleReferenceImages(job).length;

  pushUnique(items, sourceModeLabel || meta.workflow_mode_label || getWorkflowModeLabel(workflowMode));
  if (pageCount > 0) pushUnique(items, `${pageCount} 页`);
  pushUnique(items, meta.job_target_label || getJobTargetLabel(jobTarget));
  pushUnique(items, imagePresetLabel);
  pushUnique(items, imageQuality ? `质量 ${getGenerationParameterLabel('imageQuality', imageQuality)}` : '');
  if (meta.include_cover_page || job.include_cover_page) pushUnique(items, '含封面');
  if (styleReferenceCount > 0) pushUnique(items, `${styleReferenceCount} 张风格图`);
  pushUnique(
    items,
    generationOptions.reference_style_adherence
      ? `风格约束 ${getGenerationParameterLabel('referenceStyleAdherence', generationOptions.reference_style_adherence)}`
      : '',
  );

  return compact ? items.slice(0, 4) : items;
}

export function getTaskLaunchSummaryText(job) {
  const items = buildTaskLaunchSummary(job, { compact: true });
  return items.length > 0 ? items.join(' · ') : '参数已保存';
}
