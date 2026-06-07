import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, CheckCircle2, FileText, ListChecks, Maximize2, Sparkles, X } from 'lucide-react';
import { analyzeContentCapacity } from '../../utils/contentCapacity';

const previewText = (value, length = 110) => {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
};

const ContentCapacityPanel = ({
  analysis,
  pageCount,
  compact = false,
  disabled = false,
  onUseRecommendedPageCount,
}) => {
  if (!analysis.hasContent) return null;

  const canApplyRecommended = Boolean(onUseRecommendedPageCount) && pageCount !== analysis.recommendedPageCount;
  const panelClassName = [
    'content-capacity',
    compact ? 'content-capacity--compact' : '',
    analysis.riskLevel === 'high' ? 'content-capacity--high' : '',
    analysis.riskLevel === 'medium' ? 'content-capacity--medium' : '',
  ].filter(Boolean).join(' ');

  return (
    <section className={panelClassName} aria-label="内容容量诊断">
      <div className="content-capacity__head">
        <span>
          <Sparkles size={16} />
          <strong>建议 {analysis.recommendedLabel}</strong>
        </span>
        {canApplyRecommended && (
          <button
            type="button"
            className="content-capacity__apply"
            onClick={() => onUseRecommendedPageCount(analysis.recommendedPageCount)}
            disabled={disabled}
          >
            采用建议
          </button>
        )}
      </div>

      {analysis.riskMessage ? (
        <p className="content-capacity__risk">
          <AlertTriangle size={16} />
          <span>{analysis.riskMessage}</span>
        </p>
      ) : (
        <p className="content-capacity__risk content-capacity__risk--ok">
          <CheckCircle2 size={16} />
          <span>当前页数与内容容量匹配，生成时更容易保留主要信息。</span>
        </p>
      )}

      {!compact && (
        <>
          <div className="content-capacity__stats">
            <em>{analysis.charCount} 字</em>
            <em>{analysis.unitCount} 个信息单元</em>
            {analysis.signalCount > 0 && <em>{analysis.signalCount} 个高密度信号</em>}
          </div>

          {analysis.isUnstructuredLong && (
            <p className="content-capacity__hint">原文较长且结构较少，建议先按主题拆页再生成。</p>
          )}

          {analysis.outlineItems.length > 0 && (
            <div className="content-capacity__outline">
              <span>
                <ListChecks size={15} />
                <strong>自动分点预览</strong>
              </span>
              <ul>
                {analysis.outlineItems.map((item) => (
                  <li key={`${item.label}-${item.text}`}>
                    <strong>{item.label}</strong>
                    <span>{item.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
};

const ContentEditorDialog = ({
  value,
  onChange,
  pageCount,
  maxPages,
  disabled = false,
  required = false,
  placeholder = '',
  rows = 7,
  onUseRecommendedPageCount,
}) => {
  const [open, setOpen] = useState(false);
  const analysis = useMemo(
    () => analyzeContentCapacity(value, { pageCount, maxPages }),
    [value, pageCount, maxPages],
  );
  const titlePreview = previewText(value, 34);
  const bodyPreview = previewText(value, 150);
  const modal = open ? (
    <div className="content-editor-modal" role="dialog" aria-modal="true" aria-label="编辑任务内容">
      <button type="button" className="content-editor-modal__backdrop" onClick={() => setOpen(false)} aria-label="关闭" />
      <div className="content-editor-modal__shell">
        <header className="content-editor-modal__header">
          <div>
            <span className="eyebrow">Content</span>
            <h3>编辑任务内容</h3>
          </div>
          <button type="button" className="content-editor-modal__close" onClick={() => setOpen(false)} aria-label="关闭">
            <X size={18} />
          </button>
        </header>

        <div className="content-editor-modal__body">
          <textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            required={required}
            rows={rows}
            autoFocus
          />
          <aside className="content-editor-modal__side">
            <ContentCapacityPanel
              analysis={analysis}
              pageCount={pageCount}
              disabled={disabled}
              onUseRecommendedPageCount={onUseRecommendedPageCount}
            />
          </aside>
        </div>

        <footer className="content-editor-modal__footer">
          <button type="button" className="btn btn-secondary" onClick={() => setOpen(false)}>
            取消
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setOpen(false)}>
            确认
          </button>
        </footer>
      </div>
    </div>
  ) : null;

  useEffect(() => {
    if (!open) return undefined;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  return (
    <div className="content-editor-field">
      <div className="content-editor-field__bar">
        <span>任务内容</span>
        <button type="button" className="content-editor-field__open" onClick={() => setOpen(true)} disabled={disabled}>
          <Maximize2 size={15} />
          <span>展开编辑</span>
        </button>
      </div>

      <button
        type="button"
        className="content-editor-preview"
        onClick={() => setOpen(true)}
        disabled={disabled}
        aria-label="编辑任务内容"
      >
        <FileText size={18} />
        <span>
          <strong>{titlePreview || '未填写内容'}</strong>
          <small>{bodyPreview || '等待输入完整任务内容'}</small>
        </span>
      </button>

      <ContentCapacityPanel
        analysis={analysis}
        pageCount={pageCount}
        compact
        disabled={disabled}
        onUseRecommendedPageCount={onUseRecommendedPageCount}
      />

      {modal ? createPortal(modal, document.body) : null}
    </div>
  );
};

export default ContentEditorDialog;
