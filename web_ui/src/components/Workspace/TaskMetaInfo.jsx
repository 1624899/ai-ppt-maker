import { useCallback, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { formatTaskTime, getPageCount, getStatusLabel } from '../../utils/jobPresentation';

const TOOLTIP_WIDTH = 196;
const TOOLTIP_GAP = 8;
const VIEWPORT_PADDING = 12;
const TOOLTIP_ESTIMATED_HEIGHT = 116;

function getTooltipPosition(anchorEl) {
  const rect = anchorEl.getBoundingClientRect();
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
  const maxLeft = Math.max(VIEWPORT_PADDING, viewportWidth - TOOLTIP_WIDTH - VIEWPORT_PADDING);
  const left = Math.min(Math.max(VIEWPORT_PADDING, rect.left), maxLeft);
  const bottomTop = rect.bottom + TOOLTIP_GAP;
  const top = bottomTop + TOOLTIP_ESTIMATED_HEIGHT > viewportHeight
    ? Math.max(VIEWPORT_PADDING, rect.top - TOOLTIP_ESTIMATED_HEIGHT - TOOLTIP_GAP)
    : bottomTop;

  return {
    left,
    top,
  };
}

const TaskMetaInfo = ({ job }) => {
  const tooltipId = useId();
  const [tooltipPosition, setTooltipPosition] = useState(null);
  const statusLabel = getStatusLabel(job?.status);
  const pageCount = getPageCount(job) || '-';
  const pageCountLabel = `${pageCount} 页`;
  const updatedAtLabel = formatTaskTime(job?.updated_at);
  const summary = `${statusLabel} · ${pageCountLabel} · ${updatedAtLabel}`;
  const tooltipVisible = Boolean(tooltipPosition);
  const showTooltip = useCallback((event) => {
    setTooltipPosition(getTooltipPosition(event.currentTarget));
  }, []);
  const hideTooltip = useCallback(() => {
    setTooltipPosition(null);
  }, []);

  return (
    <span
      className="task-card__meta-info"
      aria-label={`任务信息：${summary}`}
      aria-describedby={tooltipVisible ? tooltipId : undefined}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      <span className="task-card__meta-text">{summary}</span>
      {tooltipVisible && typeof document !== 'undefined' && createPortal(
        <span
          id={tooltipId}
          className="task-card__meta-tooltip"
          role="tooltip"
          style={{
            left: `${tooltipPosition.left}px`,
            top: `${tooltipPosition.top}px`,
          }}
        >
          <span>
            <small>状态</small>
            <strong>{statusLabel}</strong>
          </span>
          <span>
            <small>页数</small>
            <strong>{pageCountLabel}</strong>
          </span>
          <span>
            <small>更新时间</small>
            <strong>{updatedAtLabel}</strong>
          </span>
        </span>,
        document.body,
      )}
    </span>
  );
};

export default TaskMetaInfo;
