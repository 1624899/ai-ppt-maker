const RULES = [
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
      ? `页面内容命中“${matched.terms.find((term) => content.includes(term))}”语义，推荐使用${option?.label || value}。`
      : `根据当前要点数量和内容密度，推荐使用${option?.label || value}。`,
  };
};
