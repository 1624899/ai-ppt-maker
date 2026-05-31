import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { ImageOff, Images, X } from 'lucide-react';
import clsx from 'clsx';

const getImageLabel = (image, index) => {
  const name = String(image?.name || '').trim();
  return name || `参考图 ${index + 1}`;
};

const StyleReferenceViewer = ({ open, images, jobTitle, onClose }) => {
  const safeImages = useMemo(
    () => (Array.isArray(images) ? images.filter((image) => String(image?.url || '').trim()) : []),
    [images],
  );
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    if (!open) return undefined;

    const closeOnEscape = (event) => {
      if (event.key === 'Escape') onClose?.();
    };

    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [onClose, open]);

  if (!open) return null;

  const selectedImage = safeImages[Math.min(selectedIndex, Math.max(0, safeImages.length - 1))] || null;
  const title = String(jobTitle || '未命名任务').trim();

  return createPortal(
    <div className="style-reference-modal" role="dialog" aria-modal="true" aria-label="参考风格图">
      <button type="button" className="style-reference-modal__backdrop" aria-label="关闭参考风格图" onClick={onClose} />
      <section className="style-reference-modal__shell">
        <header className="style-reference-modal__head">
          <div>
            <span className="eyebrow">参考风格图</span>
            <h2>{title}</h2>
            <p>{safeImages.length > 0 ? `共 ${safeImages.length} 张参考图` : '当前任务没有参考风格图'}</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} title="关闭" aria-label="关闭参考风格图">
            <X size={18} />
          </button>
        </header>

        <div className="style-reference-modal__body">
          <div className="style-reference-stage">
            {selectedImage ? (
              <img src={selectedImage.url} alt={getImageLabel(selectedImage, selectedIndex)} />
            ) : (
              <div className="style-reference-empty">
                <ImageOff size={30} />
                <span>没有可预览的参考图</span>
              </div>
            )}
          </div>

          <aside className="style-reference-list" aria-label="参考风格图列表">
            {safeImages.map((image, index) => (
              <button
                type="button"
                key={`${image.url}-${index}`}
                className={clsx('style-reference-thumb', index === selectedIndex && 'is-active')}
                onClick={() => setSelectedIndex(index)}
                title={getImageLabel(image, index)}
              >
                <img src={image.url} alt={getImageLabel(image, index)} />
                <span>
                  <strong>{getImageLabel(image, index)}</strong>
                  <small>参考风格图</small>
                </span>
              </button>
            ))}
            {safeImages.length === 0 && (
              <div className="style-reference-list__empty">
                <Images size={20} />
                <span>暂无参考图</span>
              </div>
            )}
          </aside>
        </div>
      </section>
    </div>,
    document.body,
  );
};

export default StyleReferenceViewer;
