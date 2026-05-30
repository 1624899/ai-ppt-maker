import { useEffect, useRef, useState } from 'react';
import Header from '../Layout/Header';
import AgentWorkspace from './AgentWorkspace';
import ImageMarkupPanel from './ImageMarkupPanel';
import PPTStudio from './PPTStudio';
import TaskCenter from './TaskCenter';
import { useJobDetail } from '../../hooks/useJobDetail';
import { useJobs } from '../../hooks/useJobs';
import { getJobPages, getPageImage, getPageImageKind, getPageImageOptions } from '../../utils/jobPresentation';

const buildAnnotationScopeKey = (jobId, pageNo, previewType) => (
  jobId && pageNo ? `${jobId}:${pageNo}:${previewType || 'reference'}` : ''
);

const WorkspaceShell = () => {
  const { jobs, loading: jobsLoading } = useJobs();
  const [currentJobId, setCurrentJobId] = useState(null);
  const [selectedPageIndex, setSelectedPageIndex] = useState(0);
  const [selectedPreviewType, setSelectedPreviewType] = useState('reference');
  const [imageMarkupOpen, setImageMarkupOpen] = useState(false);
  const [annotationsByScope, setAnnotationsByScope] = useState({});
  const { job: currentJob, loading: jobLoading, setJob: setCurrentJob } = useJobDetail(currentJobId);
  const autoSelectedRef = useRef(false);
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

  const handleJobCreated = (job) => {
    setCurrentJob(job);
    setCurrentJobId(job.job_id);
    setSelectedPageIndex(0);
    setSelectedPreviewType('reference');
    setImageMarkupOpen(false);
  };

  const createTask = () => {
    autoSelectedRef.current = true;
    setCurrentJobId(null);
    setCurrentJob(null);
    setSelectedPreviewType('reference');
    setImageMarkupOpen(false);
  };

  const selectJob = (jobId) => {
    setCurrentJob(null);
    setCurrentJobId(jobId);
    setSelectedPageIndex(0);
    setSelectedPreviewType('reference');
    setImageMarkupOpen(false);
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
      <Header currentJob={currentJob} onCreateTask={createTask} />
      <div className="workspace-shell">
        <TaskCenter
          jobs={jobs}
          loading={jobsLoading}
          currentJobId={currentJobId}
          onSelectJob={selectJob}
          onCreateTask={createTask}
        />
        <AgentWorkspace
          currentJob={currentJob}
          selectedPageIndex={safeSelectedPageIndex}
          selectedPreviewType={selectedPreview?.key || selectedPreviewType}
          imageAnnotations={imageAnnotations}
          onSelectPage={setSelectedPageIndex}
          onJobCreated={handleJobCreated}
          onJobUpdated={setCurrentJob}
          onOpenImageMarkup={() => setImageMarkupOpen(true)}
        />
        <PPTStudio
          currentJob={currentJob}
          loading={jobLoading}
          selectedPageIndex={safeSelectedPageIndex}
          previewType={selectedPreviewType}
          imageAnnotations={imageAnnotations}
          onSelectPage={setSelectedPageIndex}
          onPreviewTypeChange={setSelectedPreviewType}
          onJobUpdated={setCurrentJob}
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
