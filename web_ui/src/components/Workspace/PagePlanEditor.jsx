import { useState } from 'react';
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Copy, SlidersHorizontal, Trash2 } from 'lucide-react';

const joinLines = (items) => (Array.isArray(items) ? items.join('\n') : '');
const splitLines = (value) => String(value || '').split('\n').map((item) => item.trim()).filter(Boolean);
const normalizeOptionValue = (value) => String(value || '').trim();

const FALLBACK_LAYOUT_FAMILY_OPTIONS = [
  { value: 'grid_n_x_m', label: '宫格卡片' },
  { value: 'timeline_horizontal', label: '横向时间线' },
  { value: 'timeline_vertical', label: '纵向时间线' },
  { value: 'hub_and_spoke', label: '中心辐射' },
  { value: 'split_left_right', label: '左右分栏' },
  { value: 'split_top_bottom', label: '上下分区' },
  { value: 'compare_dual_axis', label: '双轴对比' },
  { value: 'process_horizontal', label: '横向流程' },
  { value: 'process_vertical', label: '纵向流程' },
  { value: 'hero_with_supporting_cards', label: '主视觉卡片' },
];

const buildLayoutFamilyOptions = (rawOptions, value) => {
  const source = Array.isArray(rawOptions) && rawOptions.length > 0
    ? rawOptions
    : FALLBACK_LAYOUT_FAMILY_OPTIONS;
  const options = [];
  const seen = new Set();
  source.forEach((option) => {
    const optionValue = normalizeOptionValue(option?.value);
    if (!optionValue || seen.has(optionValue)) return;
    seen.add(optionValue);
    options.push({
      value: optionValue,
      label: normalizeOptionValue(option?.label) || optionValue,
    });
  });
  const currentValue = normalizeOptionValue(value);
  if (currentValue && !seen.has(currentValue)) {
    options.push({ value: currentValue, label: `当前值：${currentValue}` });
  }
  return options;
};

const PagePlanEditor = ({
  page,
  index,
  total,
  layoutFamilyOptions,
  onChange,
  onDuplicate,
  onDelete,
  onMove,
}) => {
  const [activeSection, setActiveSection] = useState('basic');

  const markPromptStale = (nextPage) => ({
    ...nextPage,
    reference_prompt_stale: nextPage.reference_prompt_manual ? false : true,
    elements_prompt_stale: nextPage.elements_prompt_manual ? false : true,
  });

  const updateContentField = (field, value) => {
    onChange?.(markPromptStale({ ...page, [field]: value }));
  };

  const updateReferencePrompt = (value) => {
    onChange?.({
      ...page,
      reference_prompt: value,
      reference_prompt_manual: true,
      reference_prompt_stale: false,
    });
  };

  const updateElementsPrompt = (value) => {
    onChange?.({
      ...page,
      elements_prompt: value,
      elements_prompt_manual: true,
      elements_prompt_stale: false,
    });
  };

  const resolvedLayoutFamilyOptions = buildLayoutFamilyOptions(layoutFamilyOptions, page.layout_family);
  const isBasicOpen = activeSection === 'basic';
  const isAdvancedOpen = activeSection === 'advanced';
  const hasPromptOverride = Boolean(page.reference_prompt_manual || page.elements_prompt_manual);

  return (
    <article className="page-plan-editor">
      <div className="page-plan-editor__head">
        <span>第 {page.page_no} 页</span>
        <div className="page-plan-editor__actions">
          <button type="button" aria-label="上移页面" onClick={() => onMove?.(index, -1)} disabled={index <= 0}>
            <ArrowUp size={15} />
          </button>
          <button type="button" aria-label="下移页面" onClick={() => onMove?.(index, 1)} disabled={index >= total - 1}>
            <ArrowDown size={15} />
          </button>
          <button type="button" aria-label="复制页面" onClick={() => onDuplicate?.(index)}>
            <Copy size={15} />
          </button>
          <button type="button" aria-label="删除页面" onClick={() => onDelete?.(index)} disabled={total <= 1}>
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      <div className="page-plan-editor__sections">
        <section className="page-plan-editor__section">
          <button
            type="button"
            className={`page-plan-editor__section-toggle${isBasicOpen ? ' is-active' : ''}`}
            aria-expanded={isBasicOpen}
            onClick={() => setActiveSection('basic')}
          >
            {isBasicOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span>普通编辑</span>
          </button>
          {isBasicOpen && (
            <div className="page-plan-editor__grid">
              <label className="field">
                <span>页面标题</span>
                <input value={page.title} onChange={(event) => updateContentField('title', event.target.value)} />
              </label>
              <label className="field">
                <span>版式方向</span>
                <select
                  value={normalizeOptionValue(page.layout_family)}
                  onChange={(event) => updateContentField('layout_family', event.target.value)}
                >
                  {resolvedLayoutFamilyOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label className="field field--full">
                <span>页面摘要</span>
                <textarea value={page.summary} onChange={(event) => updateContentField('summary', event.target.value)} rows={3} />
              </label>
              <label className="field">
                <span>要点</span>
                <textarea value={joinLines(page.bullets)} onChange={(event) => updateContentField('bullets', splitLines(event.target.value))} rows={5} />
              </label>
              <label className="field">
                <span>视觉建议</span>
                <textarea value={page.visual_suggestion} onChange={(event) => updateContentField('visual_suggestion', event.target.value)} rows={5} />
              </label>
            </div>
          )}
        </section>

        <section className="page-plan-editor__section">
          <button
            type="button"
            className={`page-plan-editor__section-toggle page-plan-editor__section-toggle--advanced${isAdvancedOpen ? ' is-active' : ''}`}
            aria-expanded={isAdvancedOpen}
            onClick={() => setActiveSection('advanced')}
          >
            {isAdvancedOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <SlidersHorizontal size={15} />
            <span>高级个性化改动</span>
            {hasPromptOverride && <em>已覆盖</em>}
          </button>
          {isAdvancedOpen && (
            <div className="page-plan-editor__grid">
              <label className="field field--full">
                <span>原稿图完整提示词</span>
                {page.reference_prompt_stale && !page.reference_prompt_manual && <em>页面内容已修改，保存或生成时会自动同步。</em>}
                {page.reference_prompt_manual && <em>已手动覆盖，保存或生成时会按这里的内容使用。</em>}
                <textarea value={page.reference_prompt} onChange={(event) => updateReferencePrompt(event.target.value)} rows={4} />
              </label>
              <label className="field field--full">
                <span>元素图完整示词</span>
                {page.elements_prompt_stale && !page.elements_prompt_manual && <em>页面内容已修改，保存或生成时会自动同步。</em>}
                {page.elements_prompt_manual && <em>已手动覆盖，保存或生成时会按这里的内容使用。</em>}
                <textarea value={page.elements_prompt} onChange={(event) => updateElementsPrompt(event.target.value)} rows={4} />
              </label>
            </div>
          )}
        </section>
      </div>
    </article>
  );
};

export default PagePlanEditor;
