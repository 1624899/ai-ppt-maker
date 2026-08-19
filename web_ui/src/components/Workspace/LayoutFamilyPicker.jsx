import { useMemo, useState } from 'react';
import { Check, LayoutGrid } from 'lucide-react';
import { uiClassName } from '../../utils/uiClassName';

const REASONS = {
  grid_n_x_m: '适合多个并列观点或模块', timeline_horizontal: '适合按时间从左到右推进', timeline_vertical: '适合阶段较多的时间叙事',
  process_horizontal: '适合 2-5 个连续步骤', process_vertical: '适合步骤较多或说明较长的流程', hub_and_spoke: '适合中心主题与多个分支',
  compare_dual_axis: '适合两组方案或对象对照', dashboard: '适合高密度指标总览', funnel: '适合转化、筛选和流失过程',
  gantt_chart: '适合项目排期和工期展示', swimlane: '适合跨角色或跨部门流程', org_chart: '适合组织层级与汇报关系',
  circular_cycle: '适合循环、迭代和闭环关系', bar_chart: '适合分类数值比较', line_chart: '适合连续趋势变化', pie_chart: '适合占比和构成展示',
};

const buildRecommendationReason = (option, page) => {
  const bullets = Array.isArray(page?.bullets) ? page.bullets.filter(Boolean) : [];
  const textLength = [page?.title, page?.summary, ...bullets].join('').length;
  const density = textLength >= 260 || bullets.length >= 6 ? '内容密度较高' : textLength <= 100 && bullets.length <= 3 ? '内容较精炼' : '内容密度适中';
  const layoutReason = option?.reason || REASONS[option?.value] || `适合用“${option?.label || '当前版式'}”组织页面信息`;
  return `${density}，共 ${bullets.length} 个要点；${layoutReason}。`;
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
  const recommendedOptions = useMemo(() => {
    if (!selectedOption) return options.slice(0, 5);
    const related = options.filter((option) => option.value !== selectedOption.value && option.category === selectedOption.category);
    return [selectedOption, ...related].slice(0, 5);
  }, [options, selectedOption]);
  const visibleOptions = showAll ? options.filter((option) => category === '全部' || option.category === category) : recommendedOptions;
  return <div className={uiClassName('layout-picker')}>
    {selectedOption && <div className={uiClassName('layout-picker__current')}>
      <div className={uiClassName('layout-picker__current-head')}>
        <strong>当前版式结构</strong><span>{selectedOption.label}</span>
      </div>
      <LayoutGlyph shapes={selectedOption.preview_shapes} large />
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
          title={REASONS[option.value] || '根据页面内容选择合适的结构'}>
          <span className={uiClassName('layout-picker__option-name')}>{option.label}</span>
          {selected && <Check size={13} />}
          <LayoutGlyph shapes={option.preview_shapes} />
        </button>;
      })}
    </div>
    <div className={uiClassName('layout-picker__reason')}>
      <strong>AI 推荐理由</strong>
      <span>{buildRecommendationReason(selectedOption, page)}</span>
    </div>
  </div>;
};

export default LayoutFamilyPicker;
