import { useMemo, useState } from 'react';
import { Check, LayoutGrid } from 'lucide-react';
import { uiClassName } from '../../utils/uiClassName';

const buildRecommendationReason = (option, page) => {
  const recommendation = page?.layout_recommendation || {};
  const reason = recommendation.value === option?.value ? recommendation.reason : null;
  if (reason?.content_fit) return [reason.content_fit, reason.density_fit, reason.deck_fit].filter(Boolean).join('');
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
  const recommendedOptions = useMemo(() => {
    const candidates = Array.isArray(page?.layout_candidates) ? page.layout_candidates : [];
    const ordered = candidates.map((candidate) => options.find((option) => option.value === candidate.value)).filter(Boolean);
    return ordered.length ? ordered : (selectedOption ? [selectedOption] : options.slice(0, 5));
  }, [options, page?.layout_candidates, selectedOption]);
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
          title={option.description || '根据页面内容选择合适的结构'}>
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
