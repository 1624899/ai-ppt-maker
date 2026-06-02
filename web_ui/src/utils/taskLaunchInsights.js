import { getGenerationParameterLabel } from './generationParameterLabels';

const normalizeText = (value) => String(value || '').trim();

const buildInsight = (label, value, detail) => ({
  label,
  value: normalizeText(value),
  detail,
});

export function buildTaskLaunchInsights(params = {}, { limit = Infinity } = {}) {
  const insights = [];
  const pageCount = Number(params.pageCount || 0);
  const workflowLabel = getGenerationParameterLabel('workflowMode', params.workflowMode);
  const targetLabel = getGenerationParameterLabel('jobTarget', params.jobTarget);
  const richnessLabel = getGenerationParameterLabel('pageRichnessDefault', params.pageRichnessDefault);
  const adherenceLabel = getGenerationParameterLabel('referenceStyleAdherence', params.referenceStyleAdherence);
  const imageQualityLabel = getGenerationParameterLabel('imageQuality', params.imageQuality);

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
