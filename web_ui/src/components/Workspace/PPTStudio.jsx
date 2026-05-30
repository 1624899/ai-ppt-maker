import { Download, ExternalLink, FileArchive, FileImage, FileText, Loader2, Play, Square } from 'lucide-react';
import clsx from 'clsx';
import {
  getJobMeta,
  getJobPages,
  getPageImage,
  getPageSummary,
  getPageTitle,
  getStatusLabel,
} from '../../utils/jobPresentation';

const EXPORT_FALLBACKS = [
  { key: 'pdf', label: '下载 PDF', disabled: true },
  { key: 'png', label: '下载 PNG图片包', disabled: true },
  { key: 'share', label: '复制分享链接', disabled: true },
];

const postJobAction = async (jobId, action, payload) => {
  const response = await fetch(`/api/jobs/${jobId}/${action}`, {
    method: 'POST',
    headers: payload ? { 'Content-Type': 'application/json' } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作失败');
  return data;
};

const PPTStudio = ({ currentJob, loading, selectedPageIndex, onSelectPage, onJobUpdated }) => {
  const pages = getJobPages(currentJob);
  const activePage = pages[selectedPageIndex] || pages[0];
  const activeImage = getPageImage(activePage);
  const actions = Array.isArray(currentJob?.delivery_actions) ? currentJob.delivery_actions : [];
  const meta = getJobMeta(currentJob);
  const isRunning = ['queued', 'running', 'stopping'].includes(String(currentJob?.status || ''));
  const canResume = ['interrupted', 'error'].includes(String(currentJob?.status || ''));

  const runAction = async (action, payload) => {
    if (!currentJob?.job_id) return;
    try {
      const data = await postJobAction(currentJob.job_id, action, payload);
      onJobUpdated?.(data);
    } catch (err) {
      alert(err.message || '操作失败');
    }
  };

  return (
    <aside className="workspace-panel ppt-studio">
      <div className="workspace-panel__header">
        <span className="eyebrow">PPT Studio</span>
        <h2>预览与导出</h2>
        <p>{currentJob ? `${getStatusLabel(currentJob.status)} · ${meta.job_target_label || 'PPT 输出'}` : '生成后会在这里看到实时页面。'}</p>
      </div>

      <div className="ppt-studio__body">
        <section className="studio-card preview-card">
          <div className="studio-card__head">
            <div>
              <span>当前预览</span>
              <strong>{activePage ? `第 ${activePage.page_no} 页` : '等待生成'}</strong>
            </div>
            {activeImage && (
              <a className="icon-link" href={activeImage} target="_blank" rel="noreferrer">
                <ExternalLink size={15} />
                放大
              </a>
            )}
          </div>
          <div className="slide-preview">
            {loading ? (
              <div className="preview-placeholder">
                <Loader2 className="spin" size={24} />
                <span>正在同步任务...</span>
              </div>
            ) : activeImage ? (
              <img src={activeImage} alt={getPageTitle(activePage)} />
            ) : currentJob ? (
              <div className="preview-placeholder">
                <Loader2 className="spin" size={24} />
                <span>{isRunning ? '页面生成中...' : '暂无可预览页面'}</span>
              </div>
            ) : (
              <div className="preview-placeholder preview-placeholder--empty">
                <FileImage size={26} />
                <span>等待生成初稿</span>
              </div>
            )}
          </div>
          <div className="preview-actions">
            <button type="button" disabled={!activeImage}>替换</button>
            <a className={clsx(!activeImage && 'is-disabled')} href={activeImage || undefined} download>
              下载当前页 PNG
            </a>
          </div>
        </section>

        <section className="studio-card page-structure">
          <div className="studio-card__head">
            <div>
              <span>页面结构</span>
              <strong>{pages.length || 0} 页</strong>
            </div>
          </div>
          <div className="page-list">
            {pages.length === 0 ? (
              <div className="empty-state">生成规划完成后会出现页面列表。</div>
            ) : (
              pages.map((page, index) => {
                const image = getPageImage(page);
                return (
                  <button
                    type="button"
                    key={page.page_no}
                    className={clsx('page-item', index === selectedPageIndex && 'is-active')}
                    onClick={() => onSelectPage(index)}
                  >
                    <span className="page-item__thumb">
                      {image ? <img src={image} alt="" /> : <FileText size={16} />}
                    </span>
                    <span className="page-item__text">
                      <strong>{page.page_no}. {getPageTitle(page)}</strong>
                      <small>{getPageSummary(page) || page.status || '等待内容'}</small>
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="studio-card export-card">
          <div className="studio-card__head">
            <div>
              <span>导出结果</span>
              <strong>下载与交付</strong>
            </div>
          </div>

          <div className="job-controls">
            {isRunning && currentJob?.status !== 'stopping' && (
              <button type="button" className="btn btn-secondary" onClick={() => runAction('interrupt')}>
                <Square size={16} />
                停止生成
              </button>
            )}
            {canResume && (
              <button type="button" className="btn btn-primary" onClick={() => runAction('resume')}>
                <Play size={16} />
                继续生成
              </button>
            )}
          </div>

          <div className="export-list">
            {actions.length === 0 && <div className="empty-state">完成参考图或可编辑元素后，会出现 PPTX 导出入口。</div>}
            {actions.map((action) => {
              const generated = action.generated && action.generated_file?.pptx_url;
              return (
                <div className="export-item" key={action.key}>
                  <FileArchive size={17} />
                  <span>
                    <strong>{action.label}</strong>
                    <small>{action.description}</small>
                  </span>
                  {generated ? (
                    <a className="btn btn-primary" href={action.generated_file.pptx_url} download>
                      <Download size={15} />
                      下载
                    </a>
                  ) : action.options?.length ? (
                    <div className="export-item__options">
                      {action.options.map((option) => (
                        <button
                          type="button"
                          key={option.layer_mode}
                          onClick={() => runAction('deliver', { delivery_key: action.key, layer_mode: option.layer_mode })}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <button type="button" onClick={() => runAction('deliver', { delivery_key: action.key })}>
                      生成
                    </button>
                  )}
                </div>
              );
            })}
            {EXPORT_FALLBACKS.map((item) => (
              <button type="button" className="export-fallback" key={item.key} disabled={item.disabled}>
                {item.label}
              </button>
            ))}
          </div>
        </section>
      </div>
    </aside>
  );
};

export default PPTStudio;
