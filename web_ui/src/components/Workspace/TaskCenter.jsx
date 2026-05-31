import { useCallback, useState } from 'react';
import {
  Archive,
  Edit3,
  FileImage,
  FolderKanban,
  Images,
  LayoutTemplate,
  MoreHorizontal,
  Pin,
  PinOff,
  PlusCircle,
  Trash2,
} from 'lucide-react';
import clsx from 'clsx';
import { StaggerContainer, StaggerItem, ScaleButton } from '../Motion/MotionUI';
import SlideImage from './SlideImage';
import StyleReferenceViewer from './StyleReferenceViewer';
import TaskActionMenu from './TaskActionMenu';
import TaskSkeletonList from './TaskSkeletonList';
import { formatTaskTime, getPageCount, getStatusLabel, getStyleReferenceImages } from '../../utils/jobPresentation';

const RESOURCE_LINKS = [
  { key: 'materials', label: '素材库', description: '原稿图、无文字元素图', icon: FileImage },
  { key: 'styles', label: '参考风格', description: '品牌色与风格图', icon: FolderKanban },
  { key: 'templates', label: '历史模板', description: '复用版式和导出结构', icon: LayoutTemplate },
];

const RUNNING_STATUSES = new Set(['queued', 'running', 'stopping']);

async function readJsonResponse(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `请求失败：${res.status}`);
  }
  return data;
}

const TaskCenter = ({
  jobs,
  loading,
  currentJobId,
  onSelectJob,
  onCreateTask,
  onJobRenamed,
  onJobPinned,
  onJobDeleted,
}) => {
  const [menuJobId, setMenuJobId] = useState('');
  const [renamingJobId, setRenamingJobId] = useState('');
  const [renameValue, setRenameValue] = useState('');
  const [pendingJobId, setPendingJobId] = useState('');
  const [message, setMessage] = useState('');
  const [menuAnchorEl, setMenuAnchorEl] = useState(null);
  const [styleReferenceJob, setStyleReferenceJob] = useState(null);
  const pinnedJobs = jobs
    .filter((job) => String(job.pinned_at || '').trim())
    .sort((first, second) => String(second.pinned_at || '').localeCompare(String(first.pinned_at || '')));
  const historyJobs = jobs.filter((job) => !String(job.pinned_at || '').trim());

  const closeMenu = useCallback(() => {
    setMenuJobId('');
    setMenuAnchorEl(null);
  }, []);

  const startRename = (job) => {
    setRenamingJobId(job.job_id);
    setRenameValue(job.title || '');
    closeMenu();
    setMessage('');
  };

  const cancelRename = () => {
    setRenamingJobId('');
    setRenameValue('');
  };

  const renameJob = async (job) => {
    const title = renameValue.trim();
    if (!renamingJobId) return;
    if (!title) {
      setMessage('任务名称不能为空。');
      return;
    }
    if (title === job.title) {
      cancelRename();
      return;
    }
    setPendingJobId(job.job_id);
    setMessage('');
    try {
      const updated = await fetch(`/api/jobs/${job.job_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'rename', title }),
      }).then(readJsonResponse);
      onJobRenamed?.(updated);
      cancelRename();
    } catch (err) {
      setMessage(err.message || '重命名失败');
    } finally {
      setPendingJobId('');
    }
  };

  const pinJob = async (job) => {
    setPendingJobId(job.job_id);
    setMessage('');
    try {
      const updated = await fetch(`/api/jobs/${job.job_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'pin' }),
      }).then(readJsonResponse);
      onJobPinned?.({
        ...job,
        ...updated,
        pinned_at: String(updated.pinned_at || '').trim() || new Date().toISOString(),
      });
      closeMenu();
    } catch (err) {
      setMessage(err.message || '置顶失败');
    } finally {
      setPendingJobId('');
    }
  };

  const unpinJob = async (job) => {
    setPendingJobId(job.job_id);
    setMessage('');
    try {
      const updated = await fetch(`/api/jobs/${job.job_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'unpin' }),
      }).then(readJsonResponse);
      onJobPinned?.({
        ...job,
        ...updated,
        pinned_at: '',
      });
      closeMenu();
    } catch (err) {
      setMessage(err.message || '取消置顶失败');
    } finally {
      setPendingJobId('');
    }
  };

  const deleteJob = async (job) => {
    const title = job.title || '未命名任务';
    if (!window.confirm(`确定删除“${title}”？此操作会移除任务记录和生成产物。`)) return;

    setPendingJobId(job.job_id);
    setMessage('');
    try {
      await fetch(`/api/jobs/${job.job_id}`, { method: 'DELETE' }).then(readJsonResponse);
      onJobDeleted?.(job.job_id);
      closeMenu();
    } catch (err) {
      setMessage(err.message || '删除失败');
    } finally {
      setPendingJobId('');
    }
  };

  const openStyleReferenceViewer = (job) => {
    setStyleReferenceJob(job);
    closeMenu();
    setMessage('');
  };

  const renderTaskCard = (job) => {
    const active = currentJobId === job.job_id;
    const renaming = renamingJobId === job.job_id;
    const pending = pendingJobId === job.job_id;
    const canDelete = !RUNNING_STATUSES.has(String(job.status || ''));
    const menuOpen = menuJobId === job.job_id;
    const pinned = Boolean(String(job.pinned_at || '').trim());
    const styleReferenceImages = getStyleReferenceImages(job);
    const hasStyleReferenceImages = styleReferenceImages.length > 0;
    return (
      <StaggerItem
        key={job.job_id}
        className={clsx(
          'task-card',
          active && 'is-active',
          renaming && 'is-renaming',
          menuOpen && 'is-menu-open',
        )}
      >
        <button
          type="button"
          className="task-card__main"
          onClick={() => onSelectJob(job.job_id)}
          aria-label={`打开任务：${job.title || '未命名任务'}`}
        >
          <SlideImage
            className="task-card__preview"
            src={job.preview_image}
            alt={job.title || '任务预览'}
            variant="mini"
            emptyTitle="P"
          />
          <span className="task-card__content">
            {renaming ? (
              <input
                className="task-card__rename-input"
                value={renameValue}
                autoFocus
                disabled={pending}
                onClick={(event) => event.stopPropagation()}
                onPointerDown={(event) => event.stopPropagation()}
                onChange={(event) => setRenameValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') renameJob(job);
                  if (event.key === 'Escape') cancelRename();
                }}
                onBlur={() => renameJob(job)}
              />
            ) : (
              <strong>{job.title || '未命名任务'}</strong>
            )}
            <span className="task-card__meta">
              <span className="task-card__meta-text">
                {getStatusLabel(job.status)} · {getPageCount(job) || '-'} 页 · {formatTaskTime(job.updated_at)}
              </span>
              {hasStyleReferenceImages && (
                <span className="task-card__reference-hint" title={`有 ${styleReferenceImages.length} 张参考风格图`}>
                  <Images size={13} />
                  <small>{styleReferenceImages.length}</small>
                </span>
              )}
            </span>
          </span>
        </button>

        {!renaming && (
          <div className="task-card__menu-wrap">
            <button
              type="button"
              className="task-card__menu-button"
              aria-label="任务操作"
              aria-expanded={menuOpen}
              onClick={(event) => {
                event.stopPropagation();
                if (menuOpen) {
                  closeMenu();
                } else {
                  setMenuJobId(job.job_id);
                  setMenuAnchorEl(event.currentTarget);
                }
                setMessage('');
              }}
            >
              <MoreHorizontal size={18} />
            </button>
            <TaskActionMenu open={menuOpen} anchorEl={menuAnchorEl} onClose={closeMenu}>
              <button type="button" role="menuitem" onClick={() => startRename(job)} disabled={pending}>
                <Edit3 size={18} />
                <span>重命名</span>
              </button>
              {hasStyleReferenceImages && (
                <button type="button" role="menuitem" onClick={() => openStyleReferenceViewer(job)} disabled={pending}>
                  <Images size={18} />
                  <span>参考风格图</span>
                </button>
              )}
              {pinned ? (
                <button type="button" role="menuitem" onClick={() => unpinJob(job)} disabled={pending}>
                  <PinOff size={18} />
                  <span>取消置顶</span>
                </button>
              ) : (
                <button type="button" role="menuitem" onClick={() => pinJob(job)} disabled={pending}>
                  <Pin size={18} />
                  <span>置顶</span>
                </button>
              )}
              <button
                type="button"
                role="menuitem"
                className="is-danger"
                onClick={() => deleteJob(job)}
                disabled={pending || !canDelete}
                title={canDelete ? '删除任务' : '运行中任务需要先暂停'}
              >
                <Trash2 size={18} />
                <span>删除</span>
              </button>
            </TaskActionMenu>
          </div>
        )}
      </StaggerItem>
    );
  };

  return (
    <aside className="workspace-panel task-center">
      <div className="workspace-panel__header">
        <span className="eyebrow">任务中心</span>
        <h2>围绕一份 PPT 持续协作</h2>
        <p>历史任务、项目素材和模板入口都放在这里</p>
      </div>

      <div className="task-center__body">
        <ScaleButton className="new-task-button" onClick={onCreateTask}>
          <PlusCircle size={18} />
          <span>新建 PPT 任务</span>
        </ScaleButton>

        {!loading && pinnedJobs.length > 0 && (
          <section className="task-section task-section--pinned">
            <div className="section-title">
              <Pin size={15} />
              <span>置顶</span>
            </div>
            <StaggerContainer className="task-list" itemCount={pinnedJobs.length}>
              {pinnedJobs.map(renderTaskCard)}
            </StaggerContainer>
          </section>
        )}

        <section className="task-section">
          <div className="section-title">
            <Archive size={15} />
            <span>历史任务</span>
          </div>
          <StaggerContainer className="task-list" itemCount={historyJobs.length}>
            {loading ? (
              <TaskSkeletonList />
            ) : jobs.length === 0 ? (
              <div className="empty-state">还没有任务，先从中间创建一份初稿。</div>
            ) : historyJobs.length === 0 ? (
              <div className="empty-state">历史任务都已置顶。</div>
            ) : (
              historyJobs.map(renderTaskCard)
            )}
          </StaggerContainer>
          {message && <div className="task-action-message">{message}</div>}
        </section>

        <section className="task-section task-section--resources">
          <div className="section-title">
            <FolderKanban size={15} />
            <span>素材与知识库</span>
          </div>
          <StaggerContainer className="resource-list" itemCount={RESOURCE_LINKS.length}>
            {RESOURCE_LINKS.map(({ key, label, description, icon: Icon }) => (
              <StaggerItem key={key}>
                <ScaleButton className="resource-link">
                  <Icon size={17} />
                  <span>
                    <strong>{label}</strong>
                    <small>{description}</small>
                  </span>
                </ScaleButton>
              </StaggerItem>
            ))}
          </StaggerContainer>
        </section>
      </div>
      <StyleReferenceViewer
        key={styleReferenceJob?.job_id || 'closed'}
        open={Boolean(styleReferenceJob)}
        images={getStyleReferenceImages(styleReferenceJob)}
        jobTitle={styleReferenceJob?.title || ''}
        onClose={() => setStyleReferenceJob(null)}
      />
    </aside>
  );
};

export default TaskCenter;
