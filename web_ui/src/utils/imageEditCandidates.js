const normalizePageNo = (value) => {
  const pageNo = Number(value);
  return Number.isFinite(pageNo) && pageNo > 0 ? pageNo : 0;
};

export function getImageEditCandidates(job, pageNo, previewType = '') {
  const targetPageNo = normalizePageNo(pageNo);
  if (!targetPageNo || !Array.isArray(job?.image_edit_candidates)) return [];
  const targetPreviewType = String(previewType || '').trim();
  return job.image_edit_candidates
    .map((candidate, index) => ({ candidate, index }))
    .filter((candidate) => {
      if (!candidate.candidate || typeof candidate.candidate !== 'object') return false;
      if (normalizePageNo(candidate.candidate.page_no) !== targetPageNo) return false;
      return !targetPreviewType || String(candidate.candidate.preview_type || '') === targetPreviewType;
    })
    .slice()
    .sort((a, b) => {
      const createdAtDiff = parseCandidateTime(b.candidate.created_at) - parseCandidateTime(a.candidate.created_at);
      if (createdAtDiff !== 0) return createdAtDiff;
      return b.index - a.index;
    })
    .map((item) => item.candidate);
}

export function getLatestImageEditCandidate(job, pageNo, previewType = '') {
  return getImageEditCandidates(job, pageNo, previewType)[0] || null;
}

export function isImageEditCandidateApplied(candidate) {
  return String(candidate?.status || '') === 'applied';
}

function parseCandidateTime(value) {
  const parsed = Date.parse(String(value || ''));
  return Number.isFinite(parsed) ? parsed : 0;
}
