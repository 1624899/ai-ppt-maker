import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, FilePlus2, LoaderCircle, Save } from 'lucide-react';
import { confirmJobPlan, getJobPlan, putJobPlan } from '../../utils/jobActions';
import { createBlankPagePlan, normalizePlan, renumberPlanPages } from '../../utils/planningDraft';
import { getJobMeta } from '../../utils/jobPresentation';
import { resolvePlanTitle } from '../../utils/titleExtraction';
import { getWorkflowModeLabel, isAwaitingPlanConfirmation } from '../../utils/workflowMode';
import PagePlanEditor from './PagePlanEditor';

const buildPlanFromJob = (job) => normalizePlan({
  ...(job?.plan || {}),
  title: resolvePlanTitle([job?.plan?.title, job?.title], getJobMeta(job).content),
  style_notes: job?.plan?.style_notes || getJobMeta(job).style_notes || '',
  pages: Array.isArray(job?.pages) ? job.pages : [],
});

const PlanningEditorSession = ({ currentJob, config, onJobUpdated }) => {
  const jobId = currentJob.job_id;
  const [plan, setPlan] = useState(() => buildPlanFromJob(currentJob));
  const [versions, setVersions] = useState(() => (Array.isArray(currentJob?.plan_versions) ? currentJob.plan_versions : []));
  const [confirmation, setConfirmation] = useState(() => getJobMeta(currentJob).plan_confirmation || {});
  const [loading, setLoading] = useState(Boolean(jobId));
  const [pending, setPending] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    getJobPlan(jobId)
      .then((payload) => {
        if (!alive) return;
        setPlan(normalizePlan(payload.plan));
        setVersions(Array.isArray(payload.plan_versions) ? payload.plan_versions : []);
        setConfirmation(payload.plan_confirmation || {});
      })
      .catch((err) => {
        if (alive) setError(err.message || '读取规划失败');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [jobId]);

  const planMeta = useMemo(() => {
    const modeLabel = getWorkflowModeLabel(currentJob?.job_meta?.workflow_mode || currentJob?.workflow_mode);
    const status = isAwaitingPlanConfirmation(currentJob) ? '等待确认' : confirmation.status === 'confirmed' ? '已确认' : '草案';
    return { modeLabel, status };
  }, [currentJob, confirmation.status]);

  const updatePlanField = (field, value) => {
    setPlan((current) => ({ ...current, [field]: value }));
  };

  const updatePage = (index, nextPage) => {
    setPlan((current) => ({
      ...current,
      pages: current.pages.map((page, pageIndex) => (pageIndex === index ? nextPage : page)),
    }));
  };

  const addPage = () => {
    setPlan((current) => ({
      ...current,
      pages: [...current.pages, createBlankPagePlan(current.pages.length + 1)],
    }));
  };

  const duplicatePage = (index) => {
    setPlan((current) => {
      const source = current.pages[index] || createBlankPagePlan(index + 1);
      const pages = [
        ...current.pages.slice(0, index + 1),
        { ...source, title: `${source.title} 副本` },
        ...current.pages.slice(index + 1),
      ];
      return { ...current, pages: renumberPlanPages(pages) };
    });
  };

  const deletePage = (index) => {
    setPlan((current) => ({
      ...current,
      pages: renumberPlanPages(current.pages.filter((_, pageIndex) => pageIndex !== index)),
    }));
  };

  const movePage = (index, offset) => {
    setPlan((current) => {
      const target = index + offset;
      if (target < 0 || target >= current.pages.length) return current;
      const pages = [...current.pages];
      const [page] = pages.splice(index, 1);
      pages.splice(target, 0, page);
      return { ...current, pages: renumberPlanPages(pages) };
    });
  };

  const saveDraft = async () => {
    if (!jobId || pending) return;
    setPending('save');
    setError('');
    setMessage('');
    try {
      const payload = await putJobPlan(jobId, { plan, summary: '用户保存规划草案' });
      setPlan(normalizePlan(payload.plan));
      setVersions(Array.isArray(payload.plan_versions) ? payload.plan_versions : []);
      setConfirmation(payload.plan_confirmation || {});
      setMessage('规划草案已保存');
    } catch (err) {
      setError(err.message || '保存规划失败');
    } finally {
      setPending('');
    }
  };

  const confirmPlan = async () => {
    if (!jobId || pending) return;
    setPending('confirm');
    setError('');
    setMessage('');
    try {
      const updatedJob = await confirmJobPlan(jobId, { plan, summary: '用户确认规划并继续生成' });
      onJobUpdated?.(updatedJob);
      setMessage('规划已确认，任务已继续生成');
    } catch (err) {
      setError(err.message || '确认规划失败');
    } finally {
      setPending('');
    }
  };

  return (
    <section className="planning-editor">
      <div className="planning-editor__toolbar">
        <div>
          <span>{planMeta.modeLabel} · {planMeta.status}</span>
          <strong>{plan.pages.length} 页规划</strong>
        </div>
        <div className="planning-editor__actions">
          <button type="button" className="btn btn-secondary" onClick={addPage} disabled={pending !== ''}>
            <FilePlus2 size={16} />
            新增页面
          </button>
          <button type="button" className="btn btn-secondary" onClick={saveDraft} disabled={pending !== '' || loading}>
            {pending === 'save' ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}
            保存草案
          </button>
          <button type="button" className="btn btn-primary" onClick={confirmPlan} disabled={pending !== '' || loading || plan.pages.length === 0}>
            {pending === 'confirm' ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}
            确认规划并继续生成
          </button>
        </div>
      </div>

      <div className="planning-editor__deck">
        <label className="field">
          <span>PPT 标题</span>
          <input value={plan.title} onChange={(event) => updatePlanField('title', event.target.value)} />
        </label>
        <label className="field">
          <span>目标受众</span>
          <input value={plan.audience} onChange={(event) => updatePlanField('audience', event.target.value)} />
        </label>
        <label className="field">
          <span>风格方向</span>
          <input value={plan.style_type} onChange={(event) => updatePlanField('style_type', event.target.value)} />
        </label>
        <label className="field">
          <span>风格补充</span>
          <input value={plan.style_notes} onChange={(event) => updatePlanField('style_notes', event.target.value)} />
        </label>
        <label className="field field--full">
          <span>整体摘要</span>
          <textarea value={plan.summary} onChange={(event) => updatePlanField('summary', event.target.value)} rows={4} />
        </label>
      </div>

      {error && <div className="form-error">{error}</div>}
      {message && <div className="form-success">{message}</div>}

      <div className="planning-editor__pages">
        {plan.pages.length === 0 ? (
          <div className="empty-state">当前规划还没有页面，新增一页后开始编辑。</div>
        ) : (
          plan.pages.map((page, index) => (
            <PagePlanEditor
              key={`${page.page_no}-${index}`}
              page={page}
              index={index}
              total={plan.pages.length}
              layoutFamilyOptions={config?.layout_family_options}
              onChange={(nextPage) => updatePage(index, nextPage)}
              onDuplicate={duplicatePage}
              onDelete={deletePage}
              onMove={movePage}
            />
          ))
        )}
      </div>

      {versions.length > 0 && (
        <div className="planning-editor__versions">
          <span>规划版本</span>
          {versions.slice().reverse().slice(0, 4).map((version) => (
            <strong key={version.version_id}>{version.version_id} · {version.summary || version.source}</strong>
          ))}
        </div>
      )}
    </section>
  );
};

const PlanningEditor = ({ currentJob, config, onJobUpdated }) => {
  if (!currentJob?.job_id) {
    return <div className="empty-state">创建任务后，这里会显示可编辑规划。</div>;
  }

  const sessionKey = [
    currentJob.job_id,
    currentJob.updated_at || '',
    currentJob.status || '',
  ].join(':');

  return <PlanningEditorSession key={sessionKey} currentJob={currentJob} config={config} onJobUpdated={onJobUpdated} />;
};

export default PlanningEditor;
