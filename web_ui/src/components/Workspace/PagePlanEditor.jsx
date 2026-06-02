import { ArrowDown, ArrowUp, Copy, Trash2 } from 'lucide-react';

const joinLines = (items) => (Array.isArray(items) ? items.join('\n') : '');
const splitLines = (value) => String(value || '').split('\n').map((item) => item.trim()).filter(Boolean);

const PagePlanEditor = ({
  page,
  index,
  total,
  onChange,
  onDuplicate,
  onDelete,
  onMove,
}) => {
  const updateField = (field, value) => {
    onChange?.({ ...page, [field]: value });
  };

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

      <div className="page-plan-editor__grid">
        <label className="field">
          <span>页面标题</span>
          <input value={page.title} onChange={(event) => updateField('title', event.target.value)} />
        </label>
        <label className="field">
          <span>版式方向</span>
          <input value={page.layout_family} onChange={(event) => updateField('layout_family', event.target.value)} />
        </label>
        <label className="field field--full">
          <span>页面摘要</span>
          <textarea value={page.summary} onChange={(event) => updateField('summary', event.target.value)} rows={3} />
        </label>
        <label className="field">
          <span>要点</span>
          <textarea value={joinLines(page.bullets)} onChange={(event) => updateField('bullets', splitLines(event.target.value))} rows={5} />
        </label>
        <label className="field">
          <span>视觉建议</span>
          <textarea value={page.visual_suggestion} onChange={(event) => updateField('visual_suggestion', event.target.value)} rows={5} />
        </label>
        <label className="field field--full">
          <span>原稿图提示词</span>
          <textarea value={page.reference_prompt} onChange={(event) => updateField('reference_prompt', event.target.value)} rows={4} />
        </label>
      </div>
    </article>
  );
};

export default PagePlanEditor;
