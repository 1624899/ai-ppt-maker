import { useEffect, useMemo, useReducer } from 'react';
import { confirmJobPlan, getJobPlan, putJobPlan } from '../utils/jobActions';
import { normalizePlan } from '../utils/planningDraft';
import { getJobMeta } from '../utils/jobPresentation';
import { resolvePlanTitle } from '../utils/titleExtraction';

const EMPTY_PLAN = normalizePlan({ pages: [] });

const buildPlanFromJob = (job) => normalizePlan({
  ...(job?.plan || {}),
  title: resolvePlanTitle([job?.plan?.title, job?.title], getJobMeta(job).content),
  style_notes: job?.plan?.style_notes || getJobMeta(job).style_notes || '',
  pages: Array.isArray(job?.pages) ? job.pages : [],
});

const sortForCompare = (value) => {
  if (Array.isArray(value)) {
    return value.map(sortForCompare);
  }
  if (!value || typeof value !== 'object') {
    return value;
  }
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, sortForCompare(value[key])]),
  );
};

const planFingerprint = (plan) => JSON.stringify(sortForCompare(plan || {}));

export const PLAN_CONFIRM_PENDING_KEY = 'confirm-plan';
export const PLAN_SAVE_PENDING_KEY = 'save-plan';

const INITIAL_STATE = {
  loadedJobId: '',
  loadedSnapshotKey: '',
  draft: EMPTY_PLAN,
  savedPlan: EMPTY_PLAN,
  confirmation: {},
  loading: false,
  pending: '',
  message: '',
  error: '',
};

function planningDraftReducer(state, action) {
  switch (action.type) {
    case 'reset':
      return INITIAL_STATE;
    case 'load_start':
      return {
        ...state,
        loadedJobId: action.jobId,
        loadedSnapshotKey: action.snapshotKey,
        draft: action.plan,
        savedPlan: action.plan,
        confirmation: action.confirmation,
        loading: true,
        pending: '',
        message: '',
        error: '',
      };
    case 'load_success':
      return {
        ...state,
        draft: action.plan,
        savedPlan: action.plan,
        confirmation: action.confirmation,
      };
    case 'load_error':
      return { ...state, error: action.error };
    case 'load_done':
      return { ...state, loading: false };
    case 'update_draft': {
      const nextPlan = typeof action.updater === 'function' ? action.updater(state.draft) : action.updater;
      return {
        ...state,
        draft: nextPlan && typeof nextPlan === 'object' ? nextPlan : EMPTY_PLAN,
        message: '',
        error: '',
      };
    }
    case 'save_start':
      return { ...state, pending: PLAN_SAVE_PENDING_KEY, message: '', error: '' };
    case 'save_success':
      return {
        ...state,
        draft: action.plan,
        savedPlan: action.plan,
        confirmation: action.confirmation,
        pending: '',
        message: '规划修改已保存',
      };
    case 'save_error':
      return { ...state, pending: '', error: action.error };
    case 'confirm_start':
      return { ...state, pending: PLAN_CONFIRM_PENDING_KEY, message: '', error: '' };
    case 'confirm_success':
      return {
        ...state,
        draft: action.plan,
        savedPlan: action.plan,
        confirmation: action.confirmation,
        pending: '',
        message: '规划已确认，任务已继续生成',
      };
    case 'confirm_error':
      return { ...state, pending: '', error: action.error };
    case 'discard':
      return {
        ...state,
        draft: state.savedPlan,
        message: '已放弃未保存修改',
        error: '',
      };
    default:
      return state;
  }
}

export function usePlanningDraft(currentJob, onJobUpdated) {
  const jobId = currentJob?.job_id || '';
  const [state, dispatch] = useReducer(planningDraftReducer, INITIAL_STATE);
  const {
    loadedJobId,
    loadedSnapshotKey,
    draft,
    savedPlan,
    confirmation,
    loading,
    pending,
    message,
    error,
  } = state;
  const jobSnapshotKey = useMemo(() => {
    if (!jobId) return '';
    return [
      jobId,
      currentJob?.status || '',
      currentJob?.current_stage || '',
      currentJob?.updated_at || '',
      planFingerprint(buildPlanFromJob(currentJob)),
    ].join(':');
  }, [currentJob, jobId]);

  const dirty = useMemo(() => (
    Boolean(jobId) && planFingerprint(draft) !== planFingerprint(savedPlan)
  ), [draft, jobId, savedPlan]);

  useEffect(() => {
    if (!jobId) {
      dispatch({ type: 'reset' });
      return;
    }
    if (loadedJobId === jobId && dirty) return;
    if (loadedJobId === jobId && loadedSnapshotKey === jobSnapshotKey) return;

    let alive = true;
    const initialPlan = buildPlanFromJob(currentJob);
    dispatch({
      type: 'load_start',
      jobId,
      snapshotKey: jobSnapshotKey,
      plan: initialPlan,
      confirmation: getJobMeta(currentJob).plan_confirmation || {},
    });

    getJobPlan(jobId)
      .then((payload) => {
        if (!alive) return;
        const normalizedPlan = normalizePlan(payload.plan);
        dispatch({
          type: 'load_success',
          plan: normalizedPlan,
          confirmation: payload.plan_confirmation || {},
        });
      })
      .catch((err) => {
        if (alive) dispatch({ type: 'load_error', error: err.message || '读取规划失败' });
      })
      .finally(() => {
        if (alive) dispatch({ type: 'load_done' });
      });

    return () => {
      alive = false;
    };
  }, [currentJob, dirty, jobId, jobSnapshotKey, loadedJobId, loadedSnapshotKey]);

  const updateDraft = (updater) => {
    dispatch({ type: 'update_draft', updater });
  };

  const saveDraft = async () => {
    if (!jobId || pending) return null;
    dispatch({ type: 'save_start' });
    try {
      const payload = await putJobPlan(jobId, { plan: draft, summary: '用户保存规划修改' });
      const normalizedPlan = normalizePlan(payload.plan);
      dispatch({
        type: 'save_success',
        plan: normalizedPlan,
        confirmation: payload.plan_confirmation || {},
      });
      return payload;
    } catch (err) {
      dispatch({ type: 'save_error', error: err.message || '保存规划失败' });
      return null;
    }
  };

  const confirmPlan = async ({ useSavedPlan = false } = {}) => {
    if (!jobId || pending) return null;
    const planToConfirm = normalizePlan(useSavedPlan ? savedPlan : draft);
    dispatch({ type: 'confirm_start' });
    try {
      const updatedJob = await confirmJobPlan(jobId, {
        plan: planToConfirm,
        summary: useSavedPlan
          ? '用户放弃未保存修改并按已保存规划继续生成'
          : '用户确认当前规划并继续生成',
      });
      const confirmedPlan = buildPlanFromJob(updatedJob);
      dispatch({
        type: 'confirm_success',
        plan: confirmedPlan,
        confirmation: getJobMeta(updatedJob).plan_confirmation || {},
      });
      onJobUpdated?.(updatedJob);
      return updatedJob;
    } catch (err) {
      dispatch({ type: 'confirm_error', error: err.message || '确认规划失败' });
      return null;
    }
  };

  const discardDraft = () => {
    dispatch({ type: 'discard' });
  };

  return {
    draft,
    savedPlan,
    confirmation,
    loading,
    pending,
    message,
    error,
    dirty,
    updateDraft,
    saveDraft,
    confirmPlan,
    discardDraft,
  };
}
