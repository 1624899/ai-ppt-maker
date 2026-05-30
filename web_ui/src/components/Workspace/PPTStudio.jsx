import { Download, ExternalLink, FileArchive, Play, Square } from 'lucide-react';
import clsx from 'clsx';
import FeaturePending from './FeaturePending';
import SlideImage from './SlideImage';
import {
  getJobMeta,
  getJobPages,
  getPageImage,
  getPageImageKind,
  getPageSummary,
  getPageTitle,
  getStatusLabel,
} from '../../utils/jobPresentation';

const EXPORT_FALLBACKS = [
  { key: 'pdf', label: '下载 PDF', description: '后端导出接口待接入' },
  { key: 'png', label: '下载 PNG 图片包', description: '后端导出接口待接入' },
  { key: 'share', label: '复制分享链接', description: '分享服务待接入' },
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
  const activeImageKind = getPageImageKind(activePage);
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
              <strong>{activePage ? `第 ${activePage.page_no} 页${activeImageKind ? ` · ${activeImageKind}` : ''}` : '等待生成'}</strong>
            </div>
            {activeImage && (
              <a className="icon-link" href={activeImage} target="_blank" rel="noreferrer">
                <ExternalLink size={15} />
                放大
              </a>
            )}
          </div>
          <SlideImage
            src={activeImage}
            alt={activePage ? getPageTitle(activePage) : 'PPT 页面预览'}
            loading={loading || (currentJob && isRunning && !activeImage)}
            emptyTitle={currentJob ? (isRunning ? '页面生成中' : '暂无可预览页面') : '等待生成初稿'}
            emptyDescription={currentJob ? '规划或图片产物完成后会自动同步到这里。' : '创建任务后，右侧会成为实时预览控制台。'}
            sourceLabel={activeImageKind}
            showMeta
          />
          <div className="preview-actions">
            <button type="button" disabled title="替换图片的后端接口尚未接入">替换</button>
            <a className={clsx(!activeImage && 'is-disabled')} href={activeImage || undefined} download>
              下载当前页 PNG
            </a>
          </div>
          <FeaturePending compact title="替换图片待接入">
            当前版本先支持查看与下载已生成图片，替换会在后端编辑接口完成后开放。
          </FeaturePending>
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
                    <SlideImage
                      className="page-item__thumb"
                      src={image}
                      alt={getPageTitle(page)}
                      variant="mini"
                      emptyTitle={String(page.page_no)}
                    />
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
              <button type="button" className="export-fallback" key={item.key} disabled title={item.description}>
                <span>{item.label}</span>
                <small>{item.description}</small>
              </button>
            ))}
          </div>
        </section>
      </div>
    </aside>
  );
};

export default PPTStudio;
