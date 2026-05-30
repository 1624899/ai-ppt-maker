import clsx from 'clsx';

const ImagePreviewSwitch = ({ options, value, onChange, className, label = '图片预览类型' }) => {
  const items = Array.isArray(options) ? options : [];

  if (items.length === 0) return null;

  return (
    <div className={clsx('image-preview-switch', className)} role="tablist" aria-label={label}>
      {items.map((option) => {
        const disabled = option.disabled || !option.src;
        return (
          <button
            type="button"
            key={option.key}
            role="tab"
            aria-selected={value === option.key}
            className={clsx(value === option.key && 'is-active')}
            disabled={disabled}
            title={disabled ? `${option.label}暂不可用` : `切换到${option.label}`}
            onClick={() => onChange(option.key)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
};

export default ImagePreviewSwitch;
