import { useState } from 'react';
import { ChevronDown, CheckCircle2, Circle, Loader2, TriangleAlert } from 'lucide-react';
import clsx from 'clsx';
import {
  STAGE_DEFINITIONS,
  getCompletedStageCount,
  getProgressPercent,
  getStageActivityText,
  getStageLabel,
  getStatusLabel,
} from '../../utils/jobPresentation';

const resolveStages = (job) => {
  const stageMap = new Map((Array.isArray(job?.stages) ? job.stages : []).map((stage) => [stage.key, stage]));
  return STAGE_DEFINITIONS.map((definition) => ({
    ...definition,
    ...(stageMap.get(definition.key) || {}),
    label: getStageLabel(definition.key, job?.stages || []),
  }));
};

const StageIcon = ({ status }) => {
  if (status === 'completed' || status === 'skipped') return <CheckCircle2 size={15} />;
  if (status === 'running' || status === 'stopping') return <Loader2 size={15} className="spin" />;
  if (status === 'error' || status === 'interrupted') return <TriangleAlert size={15} />;
  return <Circle size={15} />;
};

const StageProgress = ({ job, dense = false }) => {
  const [expanded, setExpanded] = useState(false);
  const stages = resolveStages(job);
  const percent = getProgressPercent(job);
  const completedCount = getCompletedStageCount(job);
  const status = getStatusLabel(job?.status);

  return (
    <div className={clsx('stage-progress', dense && 'stage-progress--dense')}>
      <button type="button" className="stage-progress__summary" onClick={() => setExpanded((value) => !value)}>
        <span>
          生成进度
          <strong>{status}</strong>
        </span>
        <span className="stage-progress__count">{completedCount}/{stages.length}</span>
        <ChevronDown className={clsx('stage-progress__chevron', expanded && 'is-open')} size={16} />
      </button>
      <div className="stage-progress__bar">
        <span style={{ width: `${percent}%` }} />
      </div>
      <div className="stage-progress__steps" aria-label="任务阶段">
        {stages.map((stage) => (
          <span
            key={stage.key}
            className={clsx('stage-progress__step', `is-${stage.status || 'pending'}`)}
            title={getStageActivityText(stage) || stage.label}
          >
            <StageIcon status={stage.status} />
            <span>{stage.label}</span>
          </span>
        ))}
      </div>
      {expanded && (
        <div className="stage-progress__logs">
          {stages.map((stage) => (
            <div key={stage.key} className="stage-log">
              <strong>{stage.label}</strong>
              <span title={getStageActivityText(stage)}>{getStageActivityText(stage)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default StageProgress;
