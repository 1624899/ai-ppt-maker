import { useMemo, useState } from 'react';
import { Check, LayoutGrid } from 'lucide-react';
import { uiClassName } from '../../utils/uiClassName';

const buildRecommendationReason = (option, page) => {
  const recommendation = page?.layout_recommendation || {};
  if (recommendation.value === option?.value && recommendation.ai_reason) return recommendation.ai_reason;
  const reason = recommendation.value === option?.value ? recommendation.reason : null;
  const intentLabels = { comparison: '对比分析', process: '流程推进', timeline: '时间演进', relationship: '关系结构', data_analysis: '数据分析', product_showcase: '主视觉展示', summary: '总结结论', action_plan: '行动计划', key_message: '核心观点', cover: '开场主题' };
  if (reason?.content_fit) return [
    reason.matched_intent ? `页面意图：${intentLabels[reason.matched_intent] || reason.matched_intent}。` : '',
    reason.matched_signals?.length ? `匹配信号：${reason.matched_signals.join('、')}。` : '',
    reason.profile_description ? `${reason.profile_description}` : '',
    reason.content_fit, reason.density_fit,
    reason.avoid_for?.length ? `不建议用于：${reason.avoid_for.join('、')}。` : '',
    reason.deck_fit
  ].filter(Boolean).join('');
  return option?.description || `适合用“${option?.label || '当前版式'}”组织页面信息。`;
};

const LayoutGlyph = ({ shapes, large = false }) => <span className={uiClassName(`layout-picker__glyph${large ? ' is-large' : ''}`)} aria-hidden="true">
  {(Array.isArray(shapes) && shapes.length ? shapes : [{ kind: 'rect', left: 60, top: 100, width: 880, height: 380 }]).map((shape, index) =>
    <i key={`${shape.kind}-${index}`} className={uiClassName(`is-${shape.kind}`)} style={{
      left: `${shape.left / 10}%`, top: `${shape.top / 5.62}%`,
      width: `${shape.width / 10}%`, height: `${shape.height / 5.62}%`
    }}>{shape.label && <b>{shape.label}</b>}</i>)}
</span>;

const LayoutFamilyPicker = ({ options, value, page, onChange, disabled = false }) => {
  const [showAll, setShowAll] = useState(false);
  const [category, setCategory] = useState('全部');
  const selectedOption = options.find((option) => option.value === value) || options[0];
  const categories = useMemo(() => ['全部', ...new Set(options.map((option) => option.category || '基础'))], [options]);
  const candidates = Array.isArray(page?.layout_candidates) ? page.layout_candidates : [];
  const orderedOptions = candidates.map((candidate) => options.find((option) => option.value === candidate.value)).filter(Boolean).slice(0, 5);
  const recommendedOptions = orderedOptions.length ? orderedOptions : (selectedOption ? [selectedOption] : options.slice(0, 5));
  const visibleOptions = showAll ? options.filter((option) => category === '全部' || option.category === category) : recommendedOptions;
  const selectedDetails = selectedOption ? [
    selectedOption.description,
    selectedOption.suitable_for?.length ? `适用：${selectedOption.suitable_for.join('、')}` : '',
    selectedOption.avoid_for?.length ? `不适用：${selectedOption.avoid_for.join('、')}` : '',
    selectedOption.supports_chart ? '支持图表' : '',
    selectedOption.supports_image ? '支持图片' : '',
    selectedOption.density_levels?.length ? `信息密度：${selectedOption.density_levels.join(' / ')}` : '',
    Number.isFinite(selectedOption.min_items) ? `要点数量：${selectedOption.min_items}-${selectedOption.max_items}` : '',
    selectedOption.semantic_group ? `语义组：${selectedOption.semantic_group}` : '',
    selectedOption.related_families?.length ? `相近版式：${selectedOption.related_families.join('、')}` : '',
  ].filter(Boolean).join(' · ') : '';
  return <div className={uiClassName('layout-picker')}>
    {selectedOption && <div className={uiClassName('layout-picker__current')}>
      <div className={uiClassName('layout-picker__current-head')}>
        <strong>当前版式结构</strong><span>{selectedOption.label}</span>
      </div>
      <LayoutGlyph shapes={selectedOption.preview_shapes} large />
      <small>{selectedDetails}</small>
    </div>}
    <div className={uiClassName('layout-picker__browser-head')}>
      <strong>{showAll ? '全部版式' : 'AI 推荐候选'}</strong>
      <button type="button" onClick={() => setShowAll((current) => !current)}>
        <LayoutGrid size={14} />{showAll ? '收起人工选择' : '人工选择版式'}
      </button>
    </div>
    {showAll && <div className={uiClassName('layout-picker__categories')}>
      {categories.map((item) => <button type="button" key={item} className={uiClassName(item === category && 'is-active')} onClick={() => setCategory(item)}>{item}</button>)}
    </div>}
    <div className={uiClassName('layout-picker__options')}>
      {visibleOptions.map((option) => {
        const selected = option.value === value;
        return <button
          type="button"
          key={option.value}
          className={uiClassName(`layout-picker__option${selected ? ' is-selected' : ''}`)}
          disabled={disabled}
          onClick={() => onChange?.(option.value)}
          title={option.description || '根据页面内容选择合适的结构'}>
          <span className={uiClassName('layout-picker__option-name')}>{option.label}</span>
          {selected && <Check size={13} />}
          <LayoutGlyph shapes={option.preview_shapes} />
          <small>{option.description}</small>
        </button>;
      })}
    </div>
    <div className={uiClassName('layout-picker__reason')}>
      <strong>AI 推荐理由</strong>
      <span>{buildRecommendationReason(selectedOption, page)}</span>
      {page?.layout_report?.enabled && page.layout_report.diversity_score != null && <small>整套结构多样性：{page.layout_report.diversity_score} 分</small>}
      {page?.layout_report?.enabled && page.layout_report.issues?.length > 0 && <small>{page.layout_report.issues.join('；')}</small>}
      {page?.layout_report?.enabled && page.layout_report.suggestions?.length > 0 && <small>改进建议：{page.layout_report.suggestions.join('；')}</small>}
    </div>
  </div>;
};

export default LayoutFamilyPicker;
