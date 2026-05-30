export const STAGE_DEFINITIONS = [
  { key: 'planning', label: '模型规划' },
  { key: 'reference_generation', label: '参考图生成' },
  { key: 'elements_generation', label: '元素图生成' },
  { key: 'ppt_export', label: '可编辑元素生成' },
];

const STATUS_LABELS = {
  queued: '等待执行',
  pending: '等待中',
  running: '生成中',
  stopping: '停止中',
  interrupted: '已中断',
  completed: '已完成',
  error: '生成失败',
  skipped: '已跳过',
};

export function getStatusLabel(status) {
  return STATUS_LABELS[String(status || '').trim()] || '待处理';
}

export function getStageLabel(stageKey, stages = []) {
  const stage = stages.find((item) => item.key === stageKey);
  const definition = STAGE_DEFINITIONS.find((item) => item.key === stageKey);
  return stage?.label || definition?.label || '准备任务';
}

export function getJobTitle(job) {
  const title = String(job?.title || '').trim();
  if (title) return title;
  const content = String(job?.job_meta?.content || job?.content || '').trim();
  return content ? content.slice(0, 36) : '未命名 PPT 任务';
}

export function getJobMeta(job) {
  return job?.job_meta || {};
}

function normalizePageNo(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

function pickFirstText(...values) {
  for (const value of values) {
    const text = String(value || '').trim();
    if (text) return text;
  }
  return '';
}

function indexArtifactsByPage(items) {
  const map = new Map();
  if (!Array.isArray(items)) return map;

  items.forEach((item) => {
    if (!item || typeof item !== 'object') return;
    const pageNo = normalizePageNo(item.page_no);
    if (!pageNo) return;
    map.set(pageNo, item);
  });

  return map;
}

export function getJobPages(job) {
  const planPages = Array.isArray(job?.pages) ? job.pages : [];
  const referencesByPage = indexArtifactsByPage(job?.reference_pages);
  const elementsByPage = indexArtifactsByPage(job?.element_pages);
  const pageNumbers = new Set();

  planPages.forEach((page) => {
    const pageNo = normalizePageNo(page?.page_no);
    if (pageNo) pageNumbers.add(pageNo);
  });
  referencesByPage.forEach((_, pageNo) => pageNumbers.add(pageNo));
  elementsByPage.forEach((_, pageNo) => pageNumbers.add(pageNo));

  return [...pageNumbers]
    .sort((a, b) => a - b)
    .map((pageNo) => {
      const page = planPages.find((item) => normalizePageNo(item?.page_no) === pageNo) || {};
      const reference = referencesByPage.get(pageNo) || {};
      const element = elementsByPage.get(pageNo) || {};

      return {
        ...page,
        page_no: pageNo,
        title: pickFirstText(page.title, reference.title, element.title, `第 ${pageNo} 页`),
        summary: pickFirstText(page.summary, reference.summary, element.summary),
        reference_image: pickFirstText(page.reference_image, reference.image, reference.reference_image),
        element_image: pickFirstText(page.element_image, element.image, element.element_image),
        image: pickFirstText(page.image, element.image, reference.image),
        reference_artifact: reference,
        element_artifact: element,
      };
    });
}

export function getPageImage(page) {
  return page?.element_image || page?.reference_image || page?.image || '';
}

export function getPageImageKind(page) {
  if (page?.element_image) return '元素图';
  if (page?.reference_image) return '参考图';
  if (page?.image) return '预览图';
  return '';
}

export function getPageImageOptions(page) {
  if (!page) return [];

  const options = [
    { key: 'reference', label: '参考图', src: page.reference_image || '' },
    { key: 'element', label: '元素图', src: page.element_image || '' },
  ];

  if (page.image && page.image !== page.reference_image && page.image !== page.element_image) {
    options.push({ key: 'preview', label: '预览图', src: page.image });
  }

  return options;
}

export function getPageTitle(page) {
  const pageNo = Number(page?.page_no || 0);
  return String(page?.title || (pageNo ? `第 ${pageNo} 页` : '页面')).trim();
}

export function getPageSummary(page) {
  const summary = String(page?.summary || '').trim();
  if (summary) return summary;
  const bullets = Array.isArray(page?.bullets) ? page.bullets.filter(Boolean) : [];
  return bullets.slice(0, 3).join(' / ');
}

export function getJobOperations(job) {
  return Array.isArray(job?.operations) ? job.operations : [];
}

export function getRecentJobOperations(job, limit = 4) {
  return getJobOperations(job).slice(-Math.max(1, limit)).reverse();
}

export function getPageVersions(job, pageNo) {
  const targetPageNo = Number(pageNo || 0);
  if (!targetPageNo) return [];
  return (Array.isArray(job?.page_versions) ? job.page_versions : [])
    .filter((version) => Number(version?.page_no || 0) === targetPageNo)
    .slice()
    .reverse();
}

export function getLatestPageVersion(job, pageNo) {
  return getPageVersions(job, pageNo)[0] || null;
}

export function getOperationStatusLabel(status) {
  const labels = {
    accepted: '已记录',
    created: '已创建',
    submitted: '已提交',
    running: '执行中',
    completed: '已完成',
    error: '失败',
  };
  return labels[String(status || '').trim()] || '处理中';
}

export function getOperationExecutionLabel(execution) {
  const labels = {
    pipeline: '进入流水线',
    pending_backend: '仅记录',
  };
  return labels[String(execution || '').trim()] || '';
}

export function getPageCount(job) {
  const pages = getJobPages(job);
  if (pages.length > 0) return pages.length;
  return Number(job?.page_count || job?.job_meta?.page_count || 0);
}

export function getCompletedStageCount(job) {
  const stages = Array.isArray(job?.stages) ? job.stages : [];
  return stages.filter((stage) => stage.status === 'completed' || stage.status === 'skipped').length;
}

export function getProgressPercent(job) {
  const stages = Array.isArray(job?.stages) && job.stages.length > 0 ? job.stages : STAGE_DEFINITIONS;
  if (String(job?.status || '') === 'completed') return 100;
  if (stages.length === 0) return 0;
  return Math.round((getCompletedStageCount(job) / stages.length) * 100);
}

export function formatTaskTime(value) {
  if (!value) return '刚刚';
  const normalized = String(value).includes('T') ? String(value) : String(value).replace(' ', 'T');
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value);

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diffMs >= 0 && diffMs < minute) return '刚刚';
  if (diffMs >= 0 && diffMs < hour) return `${Math.floor(diffMs / minute)} 分钟前`;
  if (diffMs >= 0 && diffMs < day) return `${Math.floor(diffMs / hour)} 小时前`;

  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function buildAgentSummary(job) {
  if (!job) {
    return {
      title: '先创建一份 PPT 任务',
      body: '把汇报内容、页数和风格要求交给 Agent，生成初稿后再围绕单页继续打磨。',
    };
  }

  const pages = getJobPages(job);
  const status = String(job.status || '').trim();
  if (status === 'completed') {
    return {
      title: `已为你生成 ${getPageCount(job)} 页 PPT`,
      body: '可以继续选择页面做单页调整，也可以统一风格后导出可编辑 PPT。',
    };
  }
  if (status === 'error') {
    return {
      title: '生成过程中遇到错误',
      body: String(job.error || '可以查看阶段日志，修复后继续生成或基于当前参数重试。'),
    };
  }
  if (status === 'interrupted') {
    return {
      title: '任务已中断',
      body: '当前结果已保留，可以继续生成，也可以基于现有内容重新创建任务。',
    };
  }
  if (pages.length > 0) {
    return {
      title: `正在处理 ${getStageLabel(job.current_stage, job.stages)}`,
      body: '部分页面结构已经就绪，预览区会随着生成进度持续更新。',
    };
  }
  return {
    title: `任务状态：${getStatusLabel(status)}`,
    body: `当前阶段为 ${getStageLabel(job.current_stage, job.stages)}，生成结果会自动同步到右侧 Studio。`,
  };
}
