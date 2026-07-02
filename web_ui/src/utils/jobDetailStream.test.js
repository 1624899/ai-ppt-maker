import assert from 'node:assert/strict';
import { test } from 'node:test';
import { shouldKeepJobDetailStream, shouldOpenJobDetailStream } from './jobDetailStream.js';

test('shouldOpenJobDetailStream 只为当前运行中任务打开实时流', () => {
  assert.equal(
    shouldOpenJobDetailStream('job-running', { job_id: 'job-running', status: 'running' }),
    true,
  );
  assert.equal(
    shouldOpenJobDetailStream('job-running', { job_id: 'job-running', status: 'queued' }),
    true,
  );
  assert.equal(
    shouldOpenJobDetailStream('job-running', { job_id: 'job-running', status: 'stopping' }),
    true,
  );
});

test('shouldOpenJobDetailStream 不为历史任务或非当前任务打开实时流', () => {
  assert.equal(
    shouldOpenJobDetailStream('job-done', { job_id: 'job-done', status: 'completed' }),
    false,
  );
  assert.equal(
    shouldOpenJobDetailStream('job-done', { job_id: 'job-done', status: 'interrupted' }),
    false,
  );
  assert.equal(
    shouldOpenJobDetailStream('job-done', { job_id: 'other-job', status: 'running' }),
    false,
  );
  assert.equal(shouldOpenJobDetailStream('', { job_id: 'job-done', status: 'running' }), false);
});

test('shouldKeepJobDetailStream 在已中断但后台收尾时继续等待最终状态', () => {
  const waitingJob = {
    job_id: 'job-pausing',
    status: 'interrupted',
    resume_control: { is_waiting_for_stop: true },
  };
  const readyJob = {
    job_id: 'job-pausing',
    status: 'interrupted',
    resume_control: { is_waiting_for_stop: false },
  };

  assert.equal(shouldOpenJobDetailStream('job-pausing', waitingJob), true);
  assert.equal(shouldKeepJobDetailStream(waitingJob), true);
  assert.equal(shouldKeepJobDetailStream(readyJob), false);
});
