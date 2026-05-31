import { useState } from 'react';
import { FileImage, ImageOff, Loader2 } from 'lucide-react';
import clsx from 'clsx';

const isMiniVariant = (variant) => variant === 'mini';

const SlideImage = ({
  src,
  alt,
  variant = 'preview',
  className,
  loading = false,
  emptyTitle = '等待生成',
  emptyDescription = '生成完成后会自动显示页面预览。',
  errorTitle = '预览加载失败',
  sourceLabel,
  showMeta = false,
}) => {
  const [loadedImage, setLoadedImage] = useState({ src: '', size: null });
  const [failedSrc, setFailedSrc] = useState('');

  const loaded = Boolean(src) && loadedImage.src === src;
  const failed = Boolean(src) && failedSrc === src;
  const loadState = failed ? 'error' : loaded ? 'loaded' : src ? 'loading' : 'empty';
  const size = loaded ? loadedImage.size : null;

  const showImage = Boolean(src) && loadState !== 'error';
  const showLoading = Boolean(loading || loadState === 'loading');
  const showState = !src || loadState === 'error' || showLoading;

  return (
    <div
      className={clsx(
        'slide-image',
        `slide-image--${variant}`,
        loadState === 'loaded' && 'is-loaded',
        loadState === 'error' && 'is-error',
        showLoading && 'is-loading',
        className,
      )}
    >
      {showImage && (
        <img
          src={src}
          alt={alt || emptyTitle}
          onLoad={(event) => {
            setLoadedImage({
              src,
              size: {
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              },
            });
            setFailedSrc('');
          }}
          onError={() => setFailedSrc(src)}
        />
      )}

      {showState && (
        <div className="slide-image__state">
          {isMiniVariant(variant) && !src ? (
            <span className="slide-image__initial">{String(emptyTitle || 'P').slice(0, 1)}</span>
          ) : loadState === 'error' ? (
            <ImageOff size={isMiniVariant(variant) ? 16 : 26} />
          ) : showLoading ? (
            <Loader2 className="spin" size={isMiniVariant(variant) ? 16 : 24} />
          ) : (
            <FileImage size={isMiniVariant(variant) ? 16 : 26} />
          )}
          {!isMiniVariant(variant) && (
            <span>
              <strong>{loadState === 'error' ? errorTitle : emptyTitle}</strong>
              {loadState !== 'error' && emptyDescription && <small>{emptyDescription}</small>}
            </span>
          )}
        </div>
      )}

      {loadState === 'loaded' && (sourceLabel || (showMeta && size)) && (
        <div className="slide-image__meta">
          {sourceLabel && <span>{sourceLabel}</span>}
          {showMeta && size && <span>{size.width} × {size.height}</span>}
        </div>
      )}
    </div>
  );
};

export default SlideImage;
