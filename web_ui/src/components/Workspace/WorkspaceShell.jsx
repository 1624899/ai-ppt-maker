import { useEffect, useRef, useState } from 'react';
import Header from '../Layout/Header';
import AgentWorkspace from './AgentWorkspace';
import PPTStudio from './PPTStudio';
import TaskCenter from './TaskCenter';
import { useJobDetail } from '../../hooks/useJobDetail';
import { useJobs } from '../../hooks/useJobs';
import { getJobPages } from '../../utils/jobPresentation';

const WorkspaceShell = () => {
  const { jobs, loading: jobsLoading } = useJobs();
  const [currentJobId, setCurrentJobId] = useState(null);
  const [selectedPageIndex, setSelectedPageIndex] = useState(0);
  const { job: currentJob, loading: jobLoading, setJob: setCurrentJob } = useJobDetail(currentJobId);
  const autoSelectedRef = useRef(false);
  const pages = getJobPages(currentJob);
  const safeSelectedPageIndex = pages.length > 0 ? Math.min(selectedPageIndex, pages.length - 1) : 0;

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
  };

  const createTask = () => {
    autoSelectedRef.current = true;
    setCurrentJobId(null);
    setCurrentJob(null);
  };

  const selectJob = (jobId) => {
    setCurrentJob(null);
    setCurrentJobId(jobId);
    setSelectedPageIndex(0);
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
          onSelectPage={setSelectedPageIndex}
          onJobCreated={handleJobCreated}
          onJobUpdated={setCurrentJob}
        />
        <PPTStudio
          currentJob={currentJob}
          loading={jobLoading}
          selectedPageIndex={safeSelectedPageIndex}
          onSelectPage={setSelectedPageIndex}
          onJobUpdated={setCurrentJob}
        />
      </div>
    </>
  );
};

export default WorkspaceShell;
