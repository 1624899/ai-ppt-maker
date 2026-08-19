import assert from 'node:assert/strict';

import { getJobProgress, isJobActive } from './jobProgress.js';

assert.equal(isJobActive({ status: 'awaiting_plan_confirmation' }), true);
assert.equal(isJobActive({ status: 'awaiting_reference_confirmation' }), true);
assert.equal(isJobActive({ status: 'completed' }), false);
assert.equal(getJobProgress({ status: 'awaiting_reference_confirmation', stages: [] }).statusLabel, '等待确认原稿图');

console.log('jobProgress tests passed');
