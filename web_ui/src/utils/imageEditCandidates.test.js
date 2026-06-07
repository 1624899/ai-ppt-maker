import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getLatestImageEditCandidate } from './imageEditCandidates.js';

test('getLatestImageEditCandidate 在同秒候选中返回最后追加的预览', () => {
  const job = {
    image_edit_candidates: [
      {
        candidate_id: 'old-candidate',
        page_no: 2,
        preview_type: 'reference',
        created_at: '2026-06-07T10:00:00.000Z',
      },
      {
        candidate_id: 'latest-candidate',
        page_no: 2,
        preview_type: 'reference',
        created_at: '2026-06-07T10:00:00.000Z',
      },
    ],
  };

  const latest = getLatestImageEditCandidate(job, 2, 'reference');

  assert.equal(latest.candidate_id, 'latest-candidate');
});

test('getLatestImageEditCandidate 优先按创建时间返回新预览', () => {
  const job = {
    image_edit_candidates: [
      {
        candidate_id: 'old-candidate',
        page_no: 2,
        preview_type: 'reference',
        created_at: '2026-06-07T10:00:00.000Z',
      },
      {
        candidate_id: 'latest-candidate',
        page_no: 2,
        preview_type: 'reference',
        created_at: '2026-06-07T10:00:00.250Z',
      },
    ],
  };

  const latest = getLatestImageEditCandidate(job, 2, 'reference');

  assert.equal(latest.candidate_id, 'latest-candidate');
});
