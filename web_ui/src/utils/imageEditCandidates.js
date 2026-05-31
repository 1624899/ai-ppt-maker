const normalizePageNo = (value) => {
  const pageNo = Number(value);
  return Number.isFinite(pageNo) && pageNo > 0 ? pageNo : 0;
};

export function getImageEditCandidates(job, pageNo, previewType = '') {
  const targetPageNo = normalizePageNo(pageNo);
  if (!targetPageNo || !Array.isArray(job?.image_edit_candidates)) return [];
  const targetPreviewType = String(previewType || '').trim();
  return job.image_edit_candidates
    .filter((candidate) => {
      if (!candidate || typeof candidate !== 'object') return false;
      if (normalizePageNo(candidate.page_no) !== targetPageNo) return false;
      return !targetPreviewType || String(candidate.preview_type || '') === targetPreviewType;
    })
    .slice()
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
}

export function getLatestImageEditCandidate(job, pageNo, previewType = '') {
  return getImageEditCandidates(job, pageNo, previewType)[0] || null;
}

export function isImageEditCandidateApplied(candidate) {
  return String(candidate?.status || '') === 'applied';
}
