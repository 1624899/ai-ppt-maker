import { useState } from 'react';
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Copy, Lock, LockOpen, RefreshCw, SlidersHorizontal, Trash2 } from 'lucide-react';import { uiClassName } from "../../utils/uiClassName";
import LayoutFamilyPicker from './LayoutFamilyPicker';
import { recommendPageLayout } from '../../utils/pageLayoutRecommendation';

const joinLines = (items) => Array.isArray(items) ? items.join('\n') : '';
const splitLines = (value) => String(value || '').split('\n').map((item) => item.trim()).filter(Boolean);
const normalizeOptionValue = (value) => String(value || '').trim();
const chartToText = (value) => value ? (value.simple_text || JSON.stringify(value, null, 2)) : '';
const parseSimpleChart = (value) => {
  const rows = String(value || '').split('\n').map((line) => line.trim()).filter(Boolean).map((line) => {
    const parts = line.replace('：', ':').replace('，', ',').split(/[,：:]/);
    return parts.length >= 2 ? [parts[0].trim(), Number(parts[1].trim())] : null;
  }).filter((row) => row && row[0] && Number.isFinite(row[1]));
  return rows.length ? { type: 'bar', categories: rows.map((row) => row[0]), series: [{ name: '数值', values: rows.map((row) => row[1]) }], simple_text: value } : null;
};

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
{ value: 'hero_with_supporting_cards', label: '主视觉卡片' }];


const buildLayoutFamilyOptions = (rawOptions, value) => {
  const source = Array.isArray(rawOptions) && rawOptions.length > 0 ?
  rawOptions :
  FALLBACK_LAYOUT_FAMILY_OPTIONS;
  const options = [];
  const seen = new Set();
  source.forEach((option) => {
    const optionValue = normalizeOptionValue(option?.value);
    if (!optionValue || seen.has(optionValue)) return;
    seen.add(optionValue);
    options.push({
      value: optionValue,
      label: normalizeOptionValue(option?.label) || optionValue,
      reason: normalizeOptionValue(option?.reason),
      preview_slots: Array.isArray(option?.preview_slots) ? option.preview_slots : [],
      preview_shapes: Array.isArray(option?.preview_shapes) ? option.preview_shapes : [],
      category: normalizeOptionValue(option?.category) || '基础'
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
  hasReferenceImage = false,
  hasElementImage = false,
  onRegenerateReference,
  referenceRegeneratePending = false
}) => {
  const [activeSection, setActiveSection] = useState('basic');

  const markPromptStale = (nextPage) => ({
    ...nextPage,
    reference_prompt_stale: nextPage.reference_prompt_manual ? false : true,
    elements_prompt_stale: nextPage.elements_prompt_manual ? false : true
  });

  const updateContentField = (field, value, extra = {}) => {
    onChange?.(markPromptStale({ ...page, [field]: value, ...extra }));
  };

  const updateReferencePrompt = (value) => {
    onChange?.({
      ...page,
      reference_prompt: value,
      reference_prompt_manual: true,
      reference_prompt_stale: false
    });
  };

  const updateElementsPrompt = (value) => {
    onChange?.({
      ...page,
      elements_prompt: value,
      elements_prompt_manual: true,
      elements_prompt_stale: false
    });
  };
  const updateChart = (value) => {
    try {
      const parsed = value.trim().startsWith('{') ? JSON.parse(value) : parseSimpleChart(value);
      onChange?.(markPromptStale({ ...page, chart_data: parsed }));
    } catch {
      onChange?.({ ...page, chart_data_raw: value });
    }
  };

  const resolvedLayoutFamilyOptions = buildLayoutFamilyOptions(layoutFamilyOptions, page.layout_family);
  const selectLayout = (value) => updateContentField('layout_family', value, {
    layout_source: 'user', layout_user_confirmed: true,
    reference_regeneration_required: hasReferenceImage && value !== page.layout_family,
  });
  const refreshLayoutRecommendation = () => {
    if (page.layout_locked) return;
    const recommendation = recommendPageLayout(page, resolvedLayoutFamilyOptions);
    updateContentField('layout_family', recommendation.value, {
      layout_source: 'rule', layout_reason: recommendation.reason, layout_user_confirmed: false,
      reference_regeneration_required: hasReferenceImage && recommendation.value !== page.layout_family,
    });
  };
  const toggleLayoutLock = () => onChange?.({
    ...page,
    layout_locked: !page.layout_locked,
    layout_user_confirmed: !page.layout_locked ? true : page.layout_user_confirmed,
  });
  const isBasicOpen = activeSection === 'basic';
  const isAdvancedOpen = activeSection === 'advanced';
  const hasPromptOverride = Boolean(page.reference_prompt_manual || page.elements_prompt_manual);

  return (
    <article className={uiClassName("page-plan-editor")}>
      <div className={uiClassName("page-plan-editor__head")}>
        <span>第 {page.page_no} 页</span>
        <div className={uiClassName("page-plan-editor__actions")}>
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

      <div className={uiClassName("page-plan-editor__sections")}>
        <section className={uiClassName("page-plan-editor__section")}>
          <button
            type="button"
            className={uiClassName(`page-plan-editor__section-toggle${isBasicOpen ? ' is-active' : ''}`)}
            aria-expanded={isBasicOpen}
            onClick={() => setActiveSection('basic')}>
            
            {isBasicOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span>普通编辑</span>
          </button>
          {isBasicOpen &&
          <div className={uiClassName("page-plan-editor__grid")}>
              <label className={uiClassName("field")}>
                <span>页面标题</span>
                <input value={page.title} onChange={(event) => updateContentField('title', event.target.value)} />
              </label>
                <div className={uiClassName("field field--full")}>
                  <span>版式选择与推荐理由</span>
                <LayoutFamilyPicker
                  options={resolvedLayoutFamilyOptions}
                  value={normalizeOptionValue(page.layout_family)}
                  page={page}
                  disabled={Boolean(page.layout_locked)}
                  onChange={selectLayout} />
                <div className={uiClassName("layout-decision-actions")}>
                  <button type="button" onClick={refreshLayoutRecommendation} disabled={Boolean(page.layout_locked)}><RefreshCw size={14} />智能重新选择</button>
                  <button type="button" className={uiClassName(page.layout_locked && 'is-active')} onClick={toggleLayoutLock}>
                    {page.layout_locked ? <Lock size={14} /> : <LockOpen size={14} />}{page.layout_locked ? '已锁定本页版式' : '锁定本页版式'}
                  </button>
                  <small>{page.layout_source === 'user' ? '人工选择' : '智能推荐'}{page.layout_reason ? ` · ${page.layout_reason}` : ''}</small>
                  {hasReferenceImage && !hasElementImage && page.reference_regeneration_required &&
                    <button type="button" className={uiClassName("is-active")} onClick={() => onRegenerateReference?.(page.page_no)} disabled={referenceRegeneratePending}>
                      <RefreshCw size={14} />{referenceRegeneratePending ? '正在提交...' : '按当前版式重新生成原稿图'}
                    </button>}
                </div>
                </div>
              <label className={uiClassName("field field--full")}>
                <span>页面摘要</span>
                <textarea value={page.summary} onChange={(event) => updateContentField('summary', event.target.value)} rows={3} />
              </label>
              <label className={uiClassName("field")}>
                <span>要点</span>
                <textarea value={joinLines(page.bullets)} onChange={(event) => updateContentField('bullets', splitLines(event.target.value))} rows={5} />
              </label>
              <label className={uiClassName("field")}>
                <span>视觉建议</span>
                <textarea value={page.visual_suggestion} onChange={(event) => updateContentField('visual_suggestion', event.target.value)} rows={5} />
              </label>
              <label className={uiClassName("field field--full")}>
                <span>图表数据（可选）</span>
                <small className={uiClassName("field__hint")}>每行填写“分类,数值”，例如：Q1,100；Q2,120。保存后会生成可编辑图表。</small>
                <textarea value={page.chart_data_raw ?? chartToText(page.chart_data)} onChange={(event) => updateChart(event.target.value)} rows={5}
                  placeholder={'Q1,100\nQ2,120\nQ3,150'} />
              </label>
            </div>
          }
        </section>

        <section className={uiClassName("page-plan-editor__section")}>
          <button
            type="button"
            className={uiClassName(`page-plan-editor__section-toggle page-plan-editor__section-toggle--advanced${isAdvancedOpen ? ' is-active' : ''}`)}
            aria-expanded={isAdvancedOpen}
            onClick={() => setActiveSection('advanced')}>
            
            {isAdvancedOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <SlidersHorizontal size={15} />
            <span>高级个性化改动</span>
            {hasPromptOverride && <em>已覆盖</em>}
          </button>
          {isAdvancedOpen &&
          <div className={uiClassName("page-plan-editor__grid")}>
              <label className={uiClassName("field field--full")}>
                <span>原稿图完整提示词</span>
                {page.reference_prompt_stale && !page.reference_prompt_manual && <em>页面内容已修改，保存或生成时会自动同步。</em>}
                {page.reference_prompt_manual && <em>已手动覆盖，保存或生成时会按这里的内容使用。</em>}
                <textarea value={page.reference_prompt} onChange={(event) => updateReferencePrompt(event.target.value)} rows={4} />
              </label>
              <label className={uiClassName("field field--full")}>
                <span>元素图完整示词</span>
                {page.elements_prompt_stale && !page.elements_prompt_manual && <em>页面内容已修改，保存或生成时会自动同步。</em>}
                {page.elements_prompt_manual && <em>已手动覆盖，保存或生成时会按这里的内容使用。</em>}
                <textarea value={page.elements_prompt} onChange={(event) => updateElementsPrompt(event.target.value)} rows={4} />
              </label>
            </div>
          }
        </section>
      </div>
    </article>);

};

export default PagePlanEditor;
