import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mergeJobState } from './jobStateMerge.js';

test('mergeJobState 清空服务端显式作废的交付结果和下载入口', () => {
  const currentJob = {
    job_id: 'job-1',
    result: {
      deliveries: {
        editable_ppt: {
          latest: { pptx_url: '/runs/job-1/old.pptx' },
        },
      },
      editable_delivery_bundle: {
        bundle_path: 'old-bundle.json',
      },
    },
    delivery_actions: [
      {
        key: 'editable_ppt_overlay',
        generated: true,
        generated_file: { pptx_url: '/runs/job-1/old.pptx' },
      },
    ],
  };
  const incomingJob = {
    job_id: 'job-1',
    status: 'running',
    result: {
      deliveries: {},
      editable_delivery_bundle: {},
    },
    delivery_actions: [],
  };

  const merged = mergeJobState(currentJob, incomingJob);

  assert.deepEqual(merged.result.deliveries, {});
  assert.deepEqual(merged.result.editable_delivery_bundle, {});
  assert.deepEqual(merged.delivery_actions, []);
});

test('mergeJobState 在摘要更新未携带 result 时保留当前详情', () => {
  const currentJob = {
    job_id: 'job-1',
    title: '旧标题',
    result: {
      deliveries: {
        reference_ppt: { pptx_url: '/runs/job-1/reference.pptx' },
      },
      editable_delivery_bundle: {},
    },
  };
  const incomingJob = {
    job_id: 'job-1',
    title: '新标题',
    status: 'completed',
  };

  const merged = mergeJobState(currentJob, incomingJob);

  assert.equal(merged.title, '新标题');
  assert.deepEqual(merged.result, currentJob.result);
});

test('mergeJobState 在结果作废但未携带操作入口时隐藏旧下载入口', () => {
  const currentJob = {
    job_id: 'job-1',
    delivery_actions: [
      {
        key: 'editable_ppt_overlay',
        generated: true,
        generated_file: { pptx_url: '/runs/job-1/old.pptx' },
      },
    ],
  };
  const incomingJob = {
    job_id: 'job-1',
    result: {
      deliveries: {},
      editable_delivery_bundle: {},
    },
  };

  const merged = mergeJobState(currentJob, incomingJob);

  assert.deepEqual(merged.delivery_actions, []);
});
