import { useEffect, useRef, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import Header from '../Layout/Header';
import AgentWorkspace from './AgentWorkspace';
import ImageMarkupPanel from './ImageMarkupPanel';
import PPTStudio from './PPTStudio';
import TaskCenter from './TaskCenter';
import TaskLaunchPanel from './TaskLaunchPanel';
import { useJobDetail } from '../../hooks/useJobDetail';
import { useJobs } from '../../hooks/useJobs';
import { getJobPages, getPageImage, getPageImageKind, getPageImageOptions } from '../../utils/jobPresentation';
import { mergeJobState } from '../../utils/jobStateMerge';
import { getWorkflowModeFromJob, normalizeWorkflowMode, WORKFLOW_MODE_AUTO } from '../../utils/workflowMode';

const buildAnnotationScopeKey = (jobId, pageNo, previewType) => (
  jobId && pageNo ? `${jobId}:${pageNo}:${previewType || 'reference'}` : ''
);

const WorkspaceShell = () => {
  const { jobs, loading: jobsLoading, setJobs, refreshJobs } = useJobs();
  const [currentJobId, setCurrentJobId] = useState(null);
  const [selectedPageIndex, setSelectedPageIndex] = useState(0);
  const [selectedPreviewType, setSelectedPreviewType] = useState('reference');
  const [workflowMode, setWorkflowMode] = useState(WORKFLOW_MODE_AUTO);
  const [taskLaunchOpen, setTaskLaunchOpen] = useState(false);
  const [taskLaunchSourceJob, setTaskLaunchSourceJob] = useState(null);
  const [imageMarkupOpen, setImageMarkupOpen] = useState(false);
  const [annotationsByScope, setAnnotationsByScope] = useState({});
  const { job: currentJob, loading: jobLoading, setJob: setCurrentJob } = useJobDetail(currentJobId);
  const mergeCurrentJob = (jobOrUpdater) => {
    setCurrentJob((current) => {
      const incoming = typeof jobOrUpdater === 'function' ? jobOrUpdater(current) : jobOrUpdater;
      return mergeJobState(current, incoming);
    });
  };
  const autoSelectedRef = useRef(false);
  const initialLaunchShownRef = useRef(false);
  const pages = getJobPages(currentJob);
  const safeSelectedPageIndex = pages.length > 0 ? Math.min(selectedPageIndex, pages.length - 1) : 0;
  const activePage = pages[safeSelectedPageIndex] || pages[0];
  const previewOptions = getPageImageOptions(activePage);
  const selectedPreview = previewOptions.find((option) => option.key === selectedPreviewType && option.src)
    || previewOptions.find((option) => option.src)
    || null;
  const activeImage = selectedPreview?.src || getPageImage(activePage);
  const activeImageKind = selectedPreview?.label || getPageImageKind(activePage);
  const annotationScopeKey = buildAnnotationScopeKey(currentJob?.job_id, activePage?.page_no, selectedPreview?.key || selectedPreviewType);
  const imageAnnotations = annotationScopeKey ? (annotationsByScope[annotationScopeKey] || []) : [];

  useEffect(() => {
    if (!autoSelectedRef.current && !currentJobId && jobs.length > 0) {
      autoSelectedRef.current = true;
      setCurrentJobId(jobs[0].job_id);
    }
  }, [currentJobId, jobs]);

  useEffect(() => {
    if (jobsLoading || initialLaunchShownRef.current || currentJobId || jobs.length > 0 || taskLaunchOpen) return;
    initialLaunchShownRef.current = true;
    setTaskLaunchSourceJob(null);
    setWorkflowMode(WORKFLOW_MODE_AUTO);
    setTaskLaunchOpen(true);
  }, [currentJobId, jobs.length, jobsLoading, taskLaunchOpen]);

  useEffect(() => {
    if (!currentJobId) return;
    const summary = jobs.find((job) => job.job_id === currentJobId);
    if (!summary) return;
    setCurrentJob((current) => {
      if (!current || current.job_id !== currentJobId) return current;
      return mergeJobState(current, {
        ...summary,
        title: summary.title || current.title,
        pinned_at: summary.pinned_at || current.pinned_at || '',
      });
    });
  }, [currentJobId, jobs, setCurrentJob]);

  const updateWorkflowMode = (value) => {
    setWorkflowMode(normalizeWorkflowMode(value));
  };

  const handleJobCreated = (job) => {
    setCurrentJob(job);
    setCurrentJobId(job.job_id);
    setSelectedPageIndex(0);
    setSelectedPreviewType('reference');
    setTaskLaunchOpen(false);
    setTaskLaunchSourceJob(null);
    setImageMarkupOpen(false);
    refreshJobs().catch(console.error);
  };

  const createTask = () => {
    setTaskLaunchSourceJob(null);
    setWorkflowMode(WORKFLOW_MODE_AUTO);
    setTaskLaunchOpen(true);
  };

  const createTaskFromCurrent = () => {
    if (!currentJob) {
      createTask();
      return;
    }
    setTaskLaunchSourceJob(currentJob);
    setWorkflowMode(getWorkflowModeFromJob(currentJob));
    setTaskLaunchOpen(true);
  };

  const selectJob = (jobId) => {
    if (jobId === currentJobId) return;
    setCurrentJob((current) => (current?.job_id === jobId ? current : null));
    setCurrentJobId(jobId);
    setSelectedPageIndex(0);
    setSelectedPreviewType('reference');
    setImageMarkupOpen(false);
  };

  const handleJobRenamed = (job) => {
    setJobs((current) => current.map((item) => (item.job_id === job.job_id ? { ...item, ...job } : item)));
    if (currentJobId === job.job_id) {
      setCurrentJob((current) => (current ? { ...current, title: job.title } : current));
    }
    refreshJobs().catch(console.error);
  };

  const handleJobChanged = (job) => {
    setJobs((current) => current.map((item) => (item.job_id === job.job_id ? { ...item, ...job } : item)));
    if (currentJobId === job.job_id) {
      mergeCurrentJob(job);
    }
    refreshJobs().catch(console.error);
  };

  const handleJobDeleted = (jobId) => {
    const remainingJobs = jobs.filter((job) => job.job_id !== jobId);
    setJobs(remainingJobs);
    if (currentJobId === jobId) {
      const nextJob = remainingJobs[0] || null;
      setCurrentJob(null);
      setCurrentJobId(nextJob?.job_id || null);
      setSelectedPageIndex(0);
      setSelectedPreviewType('reference');
      setImageMarkupOpen(false);
      autoSelectedRef.current = Boolean(nextJob);
    }
    refreshJobs().catch(console.error);
  };

  const updateImageAnnotations = (annotations) => {
    if (!annotationScopeKey) return;
    setAnnotationsByScope((current) => ({
      ...current,
      [annotationScopeKey]: annotations,
    }));
  };

  return (
    <>
      <Header
        currentJob={currentJob}
        taskLaunchOpen={taskLaunchOpen}
        taskLaunchSourceJob={taskLaunchSourceJob}
        onCreateTask={createTask}
        onCreateTaskFromCurrent={createTaskFromCurrent}
        onCloseTaskLaunch={() => setTaskLaunchOpen(false)}
        onJobUpdated={mergeCurrentJob}
        onJobsRefresh={refreshJobs}
      />
      <div className="workspace-shell">
        <TaskCenter
          jobs={jobs}
          loading={jobsLoading}
          currentJobId={currentJobId}
          onSelectJob={selectJob}
          onCreateTask={createTask}
          onJobRenamed={handleJobRenamed}
          onJobPinned={handleJobChanged}
          onJobDeleted={handleJobDeleted}
        />
        <AnimatePresence mode="wait" initial={false}>
        {taskLaunchOpen ? (
          <TaskLaunchPanel
            key={`task-launch-${taskLaunchSourceJob?.job_id || 'new'}`}
            sourceJob={taskLaunchSourceJob}
            workflowMode={workflowMode}
            onWorkflowModeChange={updateWorkflowMode}
            onCreated={handleJobCreated}
            onClose={() => setTaskLaunchOpen(false)}
          />
        ) : (
          <AgentWorkspace
            key="agent-workspace"
            currentJob={currentJob}
            selectedPageIndex={safeSelectedPageIndex}
            selectedPreviewType={selectedPreview?.key || selectedPreviewType}
            imageAnnotations={imageAnnotations}
            onSelectPage={setSelectedPageIndex}
            onJobUpdated={mergeCurrentJob}
            onCreateTask={createTask}
            onOpenImageMarkup={() => setImageMarkupOpen(true)}
          />
        )}
        </AnimatePresence>
        <PPTStudio
          currentJob={currentJob}
          loading={jobLoading}
          selectedPageIndex={safeSelectedPageIndex}
          previewType={selectedPreviewType}
          imageAnnotations={imageAnnotations}
          onSelectPage={setSelectedPageIndex}
          onPreviewTypeChange={setSelectedPreviewType}
          onJobUpdated={mergeCurrentJob}
          onOpenImageMarkup={() => setImageMarkupOpen(true)}
        />
      </div>
      <ImageMarkupPanel
        open={imageMarkupOpen}
        image={activeImage}
        page={activePage}
        previewLabel={activeImageKind}
        annotations={imageAnnotations}
        onAnnotationsChange={updateImageAnnotations}
        onClose={() => setImageMarkupOpen(false)}
      />
    </>
  );
};

export default WorkspaceShell;
