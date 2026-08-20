const RULES = [
  { value: 'full_screen_visual', terms: ['愿景', '口号', '发布', '主题', '开场'], reason: '页面承担开场或章节定调作用，适合用大面积视觉建立重点。' },
  { value: 'big_number', terms: ['核心指标', '关键数字', '增长率', '达成率', '总额'], reason: '页面包含明确的核心数字，适合放大结论并减少干扰信息。' },
  { value: 'dashboard', terms: ['经营看板', '监控', '多项指标', '综合指标'], reason: '页面需要同时呈现多个指标，仪表盘能保持信息层级清晰。' },
  { value: 'timeline_vertical', terms: ['时间', '阶段', '历程', '年度', '月份', '季度', '发展'] },
  { value: 'process_horizontal', terms: ['流程', '步骤', '方法', '实施', '执行'] },
  { value: 'compare_dual_axis', terms: ['对比', '比较', '差异', '优劣', '方案一', '方案二'] },
  { value: 'bar_chart', terms: ['排名', '数量', '同比', '环比', '销售额', '收入'] },
  { value: 'pie_chart', terms: ['占比', '比例', '构成', '份额'] },
  { value: 'hub_and_spoke', terms: ['核心', '生态', '围绕', '中心'] },
];

export const recommendPageLayout = (page, options = []) => {
  const content = [page?.title, page?.summary, ...(Array.isArray(page?.bullets) ? page.bullets : [])].join(' ');
  const available = new Set(options.map((option) => option.value));
  const matched = RULES.find((rule) => available.has(rule.value) && rule.terms.some((term) => content.includes(term)));
  const fallback = page?.bullets?.length >= 5 && available.has('grid_n_x_m') ? 'grid_n_x_m' :
    available.has('split_left_right') ? 'split_left_right' : options[0]?.value;
  const value = matched?.value || fallback || page?.layout_family;
  const option = options.find((item) => item.value === value);
  return {
    value,
    reason: matched
      ? (matched.reason || `页面内容包含“${matched.terms.find((term) => content.includes(term))}”，${option?.label || value}更适合表达这类信息。`)
      : `当前页面有 ${page?.bullets?.length || 0} 个要点，内容密度${page?.bullets?.length >= 5 ? '较高' : '适中'}，${option?.label || value}能保持信息层级清晰。`,
  };
};
