import { getGenerationParameterLabel } from './generationParameterLabels';

const normalizeText = (value) => String(value || '').trim();

const buildInsight = (label, value, detail) => ({
  label,
  value: normalizeText(value),
  detail,
});

export function buildTaskLaunchInsights(params = {}, { limit = Infinity } = {}) {
  const insights = [];
  const sourceMode = normalizeText(params.sourceMode);
  const pageCount = Number(params.pageCount || 0);
  const workflowLabel = getGenerationParameterLabel('workflowMode', params.workflowMode);
  const targetLabel = getGenerationParameterLabel('jobTarget', params.jobTarget);
  const richnessLabel = getGenerationParameterLabel('pageRichnessDefault', params.pageRichnessDefault);
  const adherenceLabel = getGenerationParameterLabel('referenceStyleAdherence', params.referenceStyleAdherence);
  const imageQualityLabel = getGenerationParameterLabel('imageQuality', params.imageQuality);

  if (sourceMode === 'external_reference') {
    insights.push(buildInsight(
      '任务来源',
      '已有原稿图',
      '会把上传图片登记为任务原稿图，跳过模型规划和原稿图生成。',
    ));
    insights.push(buildInsight(
      '转换起点',
      params.externalReferenceCreateOnly ? '停在原稿图阶段' : '继续生成可编辑元素',
      params.externalReferenceCreateOnly
        ? '适合先归档和预览，之后可以从任务继续生成。'
        : '会直接从元素图阶段开始处理，后续生成可编辑 PPT 资源。',
    ));
    insights.push(buildInsight(
      '画幅适配',
      getExternalReferenceResizeModeLabel(params.externalReferenceResizeMode),
      params.externalReferenceResizeMode === 'contain'
        ? '会保留完整图片比例，空白区域使用系统默认背景。'
        : '会把图片规范到目标画幅，便于后续流水线统一处理。',
    ));
    if (imageQualityLabel) {
      insights.push(buildInsight(
        '元素图质量',
        imageQualityLabel,
        '质量档位会影响后续元素图转换的细节稳定性和等待时间。',
      ));
    }
    const maxItems = Number.isFinite(limit) ? Math.max(0, limit) : insights.length;
    return insights.filter((item) => item.value).slice(0, maxItems);
  }

  if (workflowLabel) {
    insights.push(buildInsight(
      '工作流节奏',
      workflowLabel,
      params.workflowMode === 'guided'
        ? '先出规划再确认，适合内容结构还需要把关的场景。'
        : '直接跑完整链路，适合方向明确、希望快速得到初稿的场景。',
    ));
  }

  if (pageCount > 0) {
    insights.push(buildInsight(
      '篇幅密度',
      `${pageCount} 页`,
      pageCount >= 8
        ? '页数偏多，会给内容拆分更多空间，也会拉长生成时间。'
        : '页数较收敛，更适合做重点表达和快速迭代。',
    ));
  }

  if (targetLabel) {
    insights.push(buildInsight(
      '交付形态',
      targetLabel,
      params.jobTarget === 'reference_only'
        ? '优先输出图片版效果稿，视觉一致性更强。'
        : '会继续生成可编辑元素，方便后续在 PPT 中细改。',
    ));
  }

  if (richnessLabel || adherenceLabel) {
    insights.push(buildInsight(
      '视觉约束',
      [richnessLabel ? `丰富度 ${richnessLabel}` : '', adherenceLabel ? `风格 ${adherenceLabel}` : '']
        .filter(Boolean)
        .join(' · '),
      adherenceLabel === '严格'
        ? '会更靠近参考风格，适合品牌规范明确的任务。'
        : '会在参考风格和内容表达之间保留一定发挥空间。',
    ));
  }

  if (imageQualityLabel) {
    insights.push(buildInsight(
      '生成成本',
      imageQualityLabel,
      params.imageQuality === 'high'
        ? '高质量会提升细节稳定性，同时整体等待时间可能更长。'
        : '当前质量档更利于快速试方向，之后可再提高细节要求。',
    ));
  }

  const maxItems = Number.isFinite(limit) ? Math.max(0, limit) : insights.length;
  return insights.filter((item) => item.value).slice(0, maxItems);
}

function getExternalReferenceResizeModeLabel(value) {
  const labels = {
    stretch: '拉伸填满',
    contain: '等比留白',
    cover: '等比裁切',
  };
  return labels[normalizeText(value)] || '拉伸填满';
}
