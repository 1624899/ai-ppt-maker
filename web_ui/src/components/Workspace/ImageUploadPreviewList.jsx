import { useEffect, useRef, useState } from 'react';
import { FileUp, Plus, X } from 'lucide-react';

const buildFileKey = (file, index) => `${file.name}-${file.size}-${file.lastModified}-${index}`;

const ImageUploadPreviewList = ({
  files,
  onChange,
  accept = 'image/*',
  disabled = false,
  emptyTitle,
  emptyHint,
  addLabel,
  itemLabel,
}) => {
  const previewUrlMap = useRef(new Map());
  const [previewItems, setPreviewItems] = useState([]);

  useEffect(() => {
    const activeFiles = new Set(files);
    for (const [file, url] of previewUrlMap.current.entries()) {
      if (!activeFiles.has(file)) {
        URL.revokeObjectURL(url);
        previewUrlMap.current.delete(file);
      }
    }

    setPreviewItems(files.map((file, index) => {
      let url = previewUrlMap.current.get(file);
      if (!url) {
        url = URL.createObjectURL(file);
        previewUrlMap.current.set(file, url);
      }
      return { file, index, url, key: buildFileKey(file, index) };
    }));
  }, [files]);

  useEffect(() => {
    const previewUrls = previewUrlMap.current;
    return () => {
      for (const url of previewUrls.values()) {
        URL.revokeObjectURL(url);
      }
      previewUrls.clear();
    };
  }, []);

  const appendFiles = (fileList) => {
    if (disabled) return;
    const nextFiles = Array.from(fileList || []);
    if (nextFiles.length === 0) return;
    onChange([...files, ...nextFiles]);
  };

  const handleInputChange = (event) => {
    appendFiles(event.target.files);
    event.target.value = '';
  };

  const removeFile = (indexToRemove) => {
    if (disabled) return;
    onChange(files.filter((_, index) => index !== indexToRemove));
  };

  const input = (
    <input
      type="file"
      multiple
      accept={accept}
      disabled={disabled}
      onChange={handleInputChange}
    />
  );

  if (files.length === 0) {
    return (
      <label className="image-upload-preview image-upload-preview--empty">
        <FileUp size={18} />
        <strong>{emptyTitle}</strong>
        <small>{emptyHint}</small>
        {input}
      </label>
    );
  }

  return (
    <div className="image-upload-preview">
      <div className="image-upload-preview__grid" role="list">
        {previewItems.map(({ file, index, url, key }) => (
          <article className="image-upload-preview__card" key={key} role="listitem">
            <div className="image-upload-preview__thumb">
              <img src={url} alt={`${itemLabel} ${index + 1}: ${file.name}`} />
              <button
                type="button"
                className="image-upload-preview__remove"
                aria-label={`移除 ${file.name}`}
                title="移除图片"
                disabled={disabled}
                onClick={() => removeFile(index)}
              >
                <X size={16} />
              </button>
            </div>
            <strong title={file.name}>{file.name}</strong>
            <small>{index + 1} / {files.length}</small>
          </article>
        ))}
        <label className="image-upload-preview__add">
          <Plus size={22} />
          <span>{addLabel}</span>
          {input}
        </label>
      </div>
    </div>
  );
};

export default ImageUploadPreviewList;
