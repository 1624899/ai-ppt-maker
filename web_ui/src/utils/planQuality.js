const DENSITY_LIMITS = { low: 3, medium: 6, high: 10 };

const textLength = (page) => [page?.title, page?.summary, ...(Array.isArray(page?.bullets) ? page.bullets : [])]
  .map((value) => String(value || '').trim())
  .join('').length;

export const evaluatePlanQuality = (plan) => {
  const pages = Array.isArray(plan?.pages) ? plan.pages : [];
  const pageScores = pages.map((page, index) => {
    const issues = [];
    const bullets = Array.isArray(page?.bullets) ? page.bullets.filter((item) => String(item || '').trim()) : [];
    const richness = String(page?.page_richness || 'medium').toLowerCase();
    const limit = DENSITY_LIMITS[richness] || DENSITY_LIMITS.medium;
    const title = String(page?.title || '').trim();
    const summary = String(page?.summary || '').trim();
    if (!title) issues.push('缺少页面标题');
    if (title.length > 24) issues.push('标题偏长，建议控制在 24 字以内');
    if (!summary && bullets.length === 0) issues.push('缺少摘要或要点');
    if (bullets.length > limit) issues.push(`要点较多（${bullets.length} 条），可能超过${richness}密度承载能力`);
    if (textLength(page) > 520 && richness !== 'high') issues.push('文字量偏大，建议拆页或提高信息密度等级');
    if (!String(page?.layout_family || '').trim()) issues.push('未选择版式');
    if (index > 0 && page.layout_family === pages[index - 1]?.layout_family) issues.push('与上一页连续使用相同版式');
    return { page_no: page?.page_no || index + 1, issues, score: Math.max(0, 1 - issues.length * 0.16) };
  });
  const issueCount = pageScores.reduce((total, page) => total + page.issues.length, 0);
  const overallScore = pages.length ? pageScores.reduce((total, page) => total + page.score, 0) / pages.length : 0;
  return {
    overallScore: Number(overallScore.toFixed(2)),
    issueCount,
    pageScores,
    passed: issueCount === 0,
    summary: pages.length ? (issueCount ? `${issueCount} 个待优化项，建议处理后再确认` : '内容结构检查通过') : '暂无页面可检查',
  };
};
