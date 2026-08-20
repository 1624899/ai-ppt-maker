import { useMemo, useState } from 'react';
import { CheckCircle2, FilePlus2, LoaderCircle, Save, WandSparkles } from 'lucide-react';
import { PLAN_CONFIRM_PENDING_KEY, PLAN_OPTIMIZE_PENDING_KEY, PLAN_SAVE_PENDING_KEY } from '../../hooks/usePlanningDraft';
import { createBlankPagePlan, normalizePlan, renumberPlanPages } from '../../utils/planningDraft';
import { getWorkflowModeLabel, isAwaitingPlanConfirmation } from '../../utils/workflowMode';
import PagePlanEditor from './PagePlanEditor';import { uiClassName } from "../../utils/uiClassName";
import { evaluatePlanQuality } from '../../utils/planQuality';
import { postJobOperation } from '../../utils/jobActions';

const EMPTY_PLAN = normalizePlan({ pages: [] });

const PlanningEditorSession = ({ currentJob, config, planningDraft, onConfirmCurrentPlan, onJobUpdated }) => {
  const plan = planningDraft?.draft || EMPTY_PLAN;
  const confirmation = planningDraft?.confirmation || {};
  const loading = Boolean(planningDraft?.loading);
  const pending = planningDraft?.pending || '';
  const message = planningDraft?.message || '';
  const error = planningDraft?.error || '';
  const dirty = Boolean(planningDraft?.dirty);
  const updateDraft = planningDraft?.updateDraft;
  const optimizeLayouts = planningDraft?.optimizeLayouts;
  const [layoutOptimization, setLayoutOptimization] = useState(null);
  const [referenceRegeneratePage, setReferenceRegeneratePage] = useState(0);
  const [referenceRegenerateError, setReferenceRegenerateError] = useState('');
  const referencePageNumbers = useMemo(() => new Set((currentJob?.reference_pages || []).map((item) => Number(item.page_no))), [currentJob]);
  const elementPageNumbers = useMemo(() => new Set((currentJob?.element_pages || []).map((item) => Number(item.page_no))), [currentJob]);

  const planMeta = useMemo(() => {
    const modeLabel = getWorkflowModeLabel(currentJob?.job_meta?.workflow_mode || currentJob?.workflow_mode);
    const dirtyLabel = dirty ? '有未保存修改' : '';
    const status = isAwaitingPlanConfirmation(currentJob) ? '等待确认' : confirmation.status === 'confirmed' ? '已确认' : '草案';
    const combinedStatus = [status, dirtyLabel].filter(Boolean).join(' · ');
    return { modeLabel, status: combinedStatus };
  }, [currentJob, confirmation.status, dirty]);
  const quality = useMemo(() => evaluatePlanQuality(plan), [plan]);

  const updatePlanField = (field, value) => {
    updateDraft?.((current) => {
      const nextPlan = { ...current, [field]: value };
      if (!['style_type', 'style_notes'].includes(field)) {
        return nextPlan;
      }
      return {
        ...nextPlan,
        pages: current.pages.map((page) => ({
          ...page,
          reference_prompt_stale: page.reference_prompt_manual ? false : true,
          elements_prompt_stale: page.elements_prompt_manual ? false : true
        }))
      };
    });
  };

  const updatePage = (index, nextPage) => {
    updateDraft?.((current) => ({
      ...current,
      pages: current.pages.map((page, pageIndex) => pageIndex === index ? nextPage : page)
    }));
  };

  const addPage = () => {
    updateDraft?.((current) => ({
      ...current,
      pages: [...current.pages, createBlankPagePlan(current.pages.length + 1)]
    }));
  };

  const duplicatePage = (index) => {
    updateDraft?.((current) => {
      const source = current.pages[index] || createBlankPagePlan(index + 1);
      const pages = [
      ...current.pages.slice(0, index + 1),
      {
        ...source,
        title: `${source.title} 副本`,
        reference_prompt_manual: false,
        elements_prompt_manual: false,
        reference_prompt_stale: true,
        elements_prompt_stale: true
      },
      ...current.pages.slice(index + 1)];

      return { ...current, pages: renumberPlanPages(pages) };
    });
  };

  const deletePage = (index) => {
    updateDraft?.((current) => ({
      ...current,
      pages: renumberPlanPages(current.pages.filter((_, pageIndex) => pageIndex !== index))
    }));
  };

  const movePage = (index, offset) => {
    updateDraft?.((current) => {
      const target = index + offset;
      if (target < 0 || target >= current.pages.length) return current;
      const pages = [...current.pages];
      const [page] = pages.splice(index, 1);
      pages.splice(target, 0, page);
      return { ...current, pages: renumberPlanPages(pages) };
    });
  };

  const saveDraft = async () => {
    await planningDraft?.saveDraft?.();
  };

  const confirmPlan = async () => {
    await onConfirmCurrentPlan?.();
  };
  const applyLayoutOptimization = async () => {
    const result = await optimizeLayouts?.();
    if (result) setLayoutOptimization(result.layout_optimization || null);
  };
  const regenerateReference = async (pageNo) => {
    if (!currentJob?.job_id || referenceRegeneratePage) return;
    setReferenceRegeneratePage(Number(pageNo));
    setReferenceRegenerateError('');
    try {
      const updatedJob = await postJobOperation(currentJob.job_id, {
        operation_type: 'page_reference_regenerate', page_no: pageNo, plan,
      });
      onJobUpdated?.(updatedJob);
    } catch (operationError) {
      setReferenceRegenerateError(operationError.message || '重新生成原稿图失败');
    } finally {
      setReferenceRegeneratePage(0);
    }
  };

  return (
    <section className={uiClassName("planning-editor")}>
      <div className={uiClassName("planning-editor__toolbar")}>
        <div>
          <span>{planMeta.modeLabel} · {planMeta.status}</span>
          <strong>{plan.pages.length} 页规划</strong>
        </div>
        <div className={uiClassName("planning-editor__actions")}>
          <button type="button" className={uiClassName("btn btn-secondary")} onClick={addPage} disabled={pending !== '' || loading}>
            <FilePlus2 size={16} />
            新增页面
          </button>
          <button type="button" className={uiClassName("btn btn-secondary")} onClick={saveDraft} disabled={pending !== '' || loading}>
            {pending === PLAN_SAVE_PENDING_KEY ? <LoaderCircle className={uiClassName("spin")} size={16} /> : <Save size={16} />}
            {pending === PLAN_SAVE_PENDING_KEY ? '保存中...' : '保存修改'}
          </button>
          <button type="button" className={uiClassName("btn btn-secondary")} onClick={applyLayoutOptimization} disabled={pending !== '' || loading || plan.pages.length < 2}>
            {pending === PLAN_OPTIMIZE_PENDING_KEY ? <LoaderCircle className={uiClassName("spin")} size={16} /> : <WandSparkles size={16} />}
            {pending === PLAN_OPTIMIZE_PENDING_KEY ? '优化中...' : '应用结构优化'}
          </button>
          <button type="button" className={uiClassName("btn btn-primary")} onClick={confirmPlan} disabled={pending !== '' || loading || plan.pages.length === 0}>
            {pending === PLAN_CONFIRM_PENDING_KEY ? <LoaderCircle className={uiClassName("spin")} size={16} /> : <CheckCircle2 size={16} />}
            {pending === PLAN_CONFIRM_PENDING_KEY ? '确认中...' : dirty ? '用当前修改继续生成' : '确认规划并继续生成'}
          </button>
        </div>
      </div>

      <div className={uiClassName("planning-editor__deck")}>
        <label className={uiClassName("field")}>
          <span>PPT 标题</span>
          <input value={plan.title} onChange={(event) => updatePlanField('title', event.target.value)} />
        </label>
        <label className={uiClassName("field")}>
          <span>目标受众</span>
          <input value={plan.audience} onChange={(event) => updatePlanField('audience', event.target.value)} />
        </label>
        <label className={uiClassName("field")}>
          <span>风格方向</span>
          <input value={plan.style_type} onChange={(event) => updatePlanField('style_type', event.target.value)} />
        </label>
        <label className={uiClassName("field")}>
          <span>风格补充</span>
          <input value={plan.style_notes} onChange={(event) => updatePlanField('style_notes', event.target.value)} />
        </label>
        <label className={uiClassName("field field--full")}>
          <span>整体摘要</span>
          <textarea value={plan.summary} onChange={(event) => updatePlanField('summary', event.target.value)} rows={4} />
        </label>
      </div>

      {error && <div className={uiClassName("form-error")}>{error}</div>}
      {referenceRegenerateError && <div className={uiClassName("form-error")}>{referenceRegenerateError}</div>}
      {message && <div className={uiClassName("form-success")}>{message}</div>}
      {layoutOptimization && <section className={uiClassName("plan-quality is-passed")}>
        <div className={uiClassName('plan-quality__head')}><strong>结构优化结果</strong><span>调整 {layoutOptimization.changed_count || 0} 页</span></div>
        {layoutOptimization.changes?.length > 0 && <div className={uiClassName('plan-quality__issues')}>
          {layoutOptimization.changes.map((change) => <div key={change.page_no}><b>第 {change.page_no} 页</b><span>{change.from} → {change.to}；{change.reason}</span></div>)}
        </div>}
      </section>}

      <section className={uiClassName(`plan-quality${quality.passed ? ' is-passed' : ''}`)}>
        <div className={uiClassName('plan-quality__head')}>
          <strong>内容质量检查</strong>
          <span>{quality.summary} · 得分 {Math.round(quality.overallScore * 100)}%</span>
        </div>
        {!quality.passed && <div className={uiClassName('plan-quality__issues')}>
          {quality.pageScores.filter((item) => item.issues.length > 0).map((item) =>
            <div key={item.page_no}><b>第 {item.page_no} 页</b><span>{item.issues.join('；')}</span></div>
          )}
        </div>}
      </section>

      <div className={uiClassName("planning-editor__pages")}>
        {plan.pages.length === 0 ?
        <div className={uiClassName("empty-state")}>当前规划还没有页面，新增一页后开始编辑。</div> :

        plan.pages.map((page, index) =>
        <PagePlanEditor
          key={`${page.page_no}-${index}`}
          page={page}
          index={index}
          total={plan.pages.length}
          layoutFamilyOptions={config?.layout_family_options}
          hasReferenceImage={referencePageNumbers.has(Number(page.page_no))}
          hasElementImage={elementPageNumbers.has(Number(page.page_no))}
          onRegenerateReference={regenerateReference}
          referenceRegeneratePending={referenceRegeneratePage === Number(page.page_no)}
          onChange={(nextPage) => updatePage(index, nextPage)}
          onDuplicate={duplicatePage}
          onDelete={deletePage}
          onMove={movePage} />

        )
        }
      </div>

    </section>);

};

const PlanningEditor = ({ currentJob, config, planningDraft, onConfirmCurrentPlan, onJobUpdated }) => {
  if (!currentJob?.job_id) {
    return <div className={uiClassName("empty-state")}>创建任务后，这里会显示可编辑规划。</div>;
  }

  const sessionKey = [
  currentJob.job_id,
  currentJob.updated_at || '',
  currentJob.status || ''].
  join(':');

  return (
    <PlanningEditorSession
      key={sessionKey}
      currentJob={currentJob}
      config={config}
      planningDraft={planningDraft}
      onJobUpdated={onJobUpdated}
      onConfirmCurrentPlan={onConfirmCurrentPlan} />);


};

export default PlanningEditor;
