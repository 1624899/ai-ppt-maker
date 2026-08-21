/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useRef, useState } from 'react';
import styles from '../styles/logViewer.module.css';

const DEFAULT_LINES = 200;

// 日志查看窗口：悬浮按钮 + 可开合面板，展示后端日志文件末尾若干行。
const LogViewerPanel = () => {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState('');
  const [lines, setLines] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const logBodyRef = useRef(null);

  const loadFiles = useCallback(async () => {
    try {
      const response = await fetch('/api/logs');
      const payload = await response.json();
      const list = Array.isArray(payload.files) ? payload.files : [];
      setFiles(list);
      setSelectedFile((current) => (current && list.some((item) => item.name === current) ? current : list[0]?.name || ''));
    } catch {
      setError('日志文件列表加载失败');
    }
  }, []);

  const loadLines = useCallback(async (name) => {
    if (!name) return;
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/logs/${encodeURIComponent(name)}?lines=${DEFAULT_LINES}`);
      const payload = await response.json();
      if (!response.ok) {
        setError(payload.error || '日志读取失败');
        setLines([]);
        return;
      }
      setLines(Array.isArray(payload.lines) ? payload.lines : []);
    } catch {
      setError('日志读取失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadFiles();
    }
  }, [open, loadFiles]);

  useEffect(() => {
    if (open && selectedFile) {
      loadLines(selectedFile);
    }
  }, [open, selectedFile, loadLines]);

  // 新日志到达后保持在底部，方便看最新记录。
  useEffect(() => {
    const body = logBodyRef.current;
    if (body) {
      body.scrollTop = body.scrollHeight;
    }
  }, [lines]);

  return (
    <>
      <button
        type="button"
        className={styles.floatingButton}
        onClick={() => setOpen((current) => !current)}
        title="查看运行日志"
      >
        {open ? '关闭日志' : '运行日志'}
      </button>
      {open && (
        <div className={styles.panel}>
          <div className={styles.toolbar}>
            <select
              className={styles.fileSelect}
              value={selectedFile}
              onChange={(event) => setSelectedFile(event.target.value)}
            >
              {files.length === 0 && <option value="">暂无日志文件</option>}
              {files.map((file) => (
                <option key={file.name} value={file.name}>{file.name}</option>
              ))}
            </select>
            <button
              type="button"
              className={styles.refreshButton}
              onClick={() => loadLines(selectedFile)}
              disabled={!selectedFile || loading}
            >
              {loading ? '加载中…' : '刷新'}
            </button>
          </div>
          {error && <div className={styles.error}>{error}</div>}
          <pre ref={logBodyRef} className={styles.logBody}>
            {lines.length === 0 && !loading ? '暂无日志' : lines.join('\n')}
          </pre>
        </div>
      )}
    </>
  );
};

export default LogViewerPanel;
