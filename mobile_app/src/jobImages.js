const IMAGE_SOURCES = [
  { field: 'reference_pages', label: '原稿图', keys: ['image', 'reference_image'] },
  { field: 'element_pages', label: '元素图', keys: ['image', 'element_image'] },
  { field: 'pages', label: '页面预览', keys: ['reference_image', 'element_image', 'image'] }
];

const getFirstUrl = (item, keys) => {
  for (const key of keys) {
    const value = String(item?.[key] || '').trim();
    if (value) return value;
  }
  return '';
};

export const collectJobImages = (job) => {
  const images = [];
  const seen = new Set();

  IMAGE_SOURCES.forEach(({ field, label, keys }) => {
    const entries = Array.isArray(job?.[field]) ? job[field] : [];
    entries.forEach((item, index) => {
      const url = getFirstUrl(item, keys);
      if (!url || seen.has(url)) return;
      seen.add(url);
      images.push({
        url,
        label,
        pageNo: Number(item?.page_no) || index + 1
      });
    });
  });

  return images.sort((left, right) => left.pageNo - right.pageNo);
};
