import { useState } from 'react';
import { MousePointer2, Trash2, X } from 'lucide-react';
import { getPageTitle } from '../../utils/jobPresentation';

const clampRatio = (value) => Math.min(1, Math.max(0, value));

const getRelativePoint = (event, element) => {
  const rect = element.getBoundingClientRect();
  return {
    x: clampRatio((event.clientX - rect.left) / rect.width),
    y: clampRatio((event.clientY - rect.top) / rect.height),
  };
};

const normalizeBox = (start, end) => {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  return {
    x,
    y,
    width: Math.abs(end.x - start.x),
    height: Math.abs(end.y - start.y),
  };
};

const boxStyle = (box) => ({
  left: `${box.x * 100}%`,
  top: `${box.y * 100}%`,
  width: `${box.width * 100}%`,
  height: `${box.height * 100}%`,
});

const ImageMarkupPanel = ({
  open,
  image,
  page,
  previewLabel = '原稿图',
  annotations,
  onAnnotationsChange,
  onClose,
}) => {
  const [dragStart, setDragStart] = useState(null);
  const [draftBox, setDraftBox] = useState(null);
  const safeAnnotations = Array.isArray(annotations) ? annotations : [];

  if (!open) return null;

  const startBox = (event) => {
    if (!image) return;
    const start = getRelativePoint(event, event.currentTarget);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setDragStart(start);
    setDraftBox({ x: start.x, y: start.y, width: 0, height: 0 });
  };

  const moveBox = (event) => {
    if (!dragStart) return;
    const current = getRelativePoint(event, event.currentTarget);
    setDraftBox(normalizeBox(dragStart, current));
  };

  const finishBox = (event) => {
    if (!dragStart) return;
    const current = getRelativePoint(event, event.currentTarget);
    const nextBox = normalizeBox(dragStart, current);
    setDragStart(null);
    setDraftBox(null);
    if (nextBox.width < 0.02 || nextBox.height < 0.02) return;
    onAnnotationsChange([
      ...safeAnnotations,
      {
        id: `annotation-${Date.now()}`,
        label: `区域 ${safeAnnotations.length + 1}`,
        box: nextBox,
      },
    ]);
  };

  const updateLabel = (annotationId, label) => {
    onAnnotationsChange(
      safeAnnotations.map((annotation) => (
        annotation.id === annotationId ? { ...annotation, label } : annotation
      )),
    );
  };

  const removeAnnotation = (annotationId) => {
    onAnnotationsChange(safeAnnotations.filter((annotation) => annotation.id !== annotationId));
  };

  return (
    <div className="markup-panel" role="dialog" aria-modal="true" aria-label="图片标注编辑">
      <div className="markup-panel__backdrop" onClick={onClose} />
      <div className="markup-panel__shell">
        <header className="markup-panel__head">
          <div>
            <span className="eyebrow">图片编辑预留页</span>
            <h2>{page ? `第 ${page.page_no} 页 · ${previewLabel}` : '原稿图标注'}</h2>
            <p>{page ? getPageTitle(page) : '后续图片编辑能力会从这里接入。'}</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭标注窗口">
            <X size={18} />
          </button>
        </header>

        <div className="markup-panel__body">
          <section className="markup-canvas-card">
            <div className="markup-canvas-card__hint">
              <MousePointer2 size={16} />
              <span>在图片上拖拽框选问题区域，标注会同步给左侧 Agent 对话用于理解“这里”“那块”。</span>
            </div>
            <div className="markup-canvas">
              {image ? (
                <div
                  className="markup-canvas__stage"
                  onPointerDown={startBox}
                  onPointerMove={moveBox}
                  onPointerUp={finishBox}
                  onPointerCancel={() => {
                    setDragStart(null);
                    setDraftBox(null);
                  }}
                >
                  <img src={image} alt={page ? getPageTitle(page) : '原稿图'} draggable="false" />
                  {safeAnnotations.map((annotation, index) => (
                    <span className="markup-box" style={boxStyle(annotation.box)} key={annotation.id}>
                      {annotation.label || `区域 ${index + 1}`}
                    </span>
                  ))}
                  {draftBox && <span className="markup-box markup-box--draft" style={boxStyle(draftBox)} />}
                </div>
              ) : (
                <div className="empty-state">当前页面还没有可标注的图片。</div>
              )}
            </div>
          </section>

          <aside className="markup-side-card">
            <div className="studio-card__head">
              <div>
                <span>标注列表</span>
                <strong>{safeAnnotations.length} 个区域</strong>
              </div>
              <button type="button" onClick={() => onAnnotationsChange([])} disabled={safeAnnotations.length === 0}>
                清空
              </button>
            </div>
            <div className="markup-list">
              {safeAnnotations.length === 0 ? (
                <div className="empty-state">拖拽图片即可创建第一个框选区域。</div>
              ) : (
                safeAnnotations.map((annotation, index) => (
                  <label className="markup-list__item" key={annotation.id}>
                    <span>区域 {index + 1}</span>
                    <input
                      value={annotation.label || ''}
                      onChange={(event) => updateLabel(annotation.id, event.target.value)}
                      placeholder="例如：右侧图标区"
                    />
                    <button type="button" onClick={() => removeAnnotation(annotation.id)}>
                      <Trash2 size={15} />
                      删除
                    </button>
                  </label>
                ))
              )}
            </div>
            <div className="markup-side-card__note">
              这里先完成“意图传达”的产品闭环；后续可以继续接入局部重绘、替换元素图、蒙版编辑等后端能力。
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};

export default ImageMarkupPanel;
