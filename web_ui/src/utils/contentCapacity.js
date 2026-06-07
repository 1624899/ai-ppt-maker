const LIST_MARKER_PATTERN = /^\s*(?:[-*•●]|\d+[、.)]|[一二三四五六七八九十]+[、.、])/;
const SENTENCE_SPLIT_PATTERN = /[\n。！？!?；;]+/;
const SIGNAL_PATTERN = /(?:\d+(?:\.\d+)?%|\d{1,4}[/-]\d{1,2}|[A-Za-z]\d+|[A-Za-z]+款|覆盖率|通过率|失败|异常|报错|缺陷|风险|阻断|原因|根因|解决|改进|响应|待解决)/g;

const OUTLINE_RULES = [
  { label: '背景与目标', keywords: ['背景', '目标', '方案', '任务', '项目', '中心', '规则'] },
  { label: '数据与现状', keywords: ['覆盖率', '通过率', '执行', '结果', '数据', '比例', '效果'] },
  { label: '问题与风险', keywords: ['问题', '缺陷', '失败', '异常', '报错', '阻断', '风险'] },
  { label: '原因归因', keywords: ['原因', '根因', '归因', '导致', '由于', '无法'] },
  { label: '响应安排', keywords: ['响应', '解决', '沟通', '同步', '处理', '待解决'] },
  { label: '预防改进', keywords: ['避免', '后续', '预防', '改进', '机制', '标准'] },
];

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const normalizeText = (value) => String(value || '').replace(/\r\n/g, '\n').trim();

const unique = (items) => {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.replace(/\s+/g, '');
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

const truncateText = (value, maxLength = 84) => {
  const text = normalizeText(value).replace(/\s+/g, ' ');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}…`;
};

const splitSegments = (text) => {
  return unique(
    text
      .split(SENTENCE_SPLIT_PATTERN)
      .map((item) => item.trim())
      .filter((item) => item.length >= 8),
  );
};

const countMatches = (text, pattern) => {
  const matches = text.match(pattern);
  return matches ? matches.length : 0;
};

const scoreSegment = (segment) => {
  let score = 0;
  if (segment.length >= 16 && segment.length <= 96) score += 1;
  if (/\d/.test(segment)) score += 1;
  if (SIGNAL_PATTERN.test(segment)) score += 2;
  SIGNAL_PATTERN.lastIndex = 0;
  if (/[：:]/.test(segment)) score += 1;
  if (/(因此|由于|导致|后续|建议|需要|当前|目前)/.test(segment)) score += 1;
  return score;
};

const buildOutlineItems = (segments) => {
  if (segments.length === 0) return [];

  const used = new Set();
  const grouped = OUTLINE_RULES.map((rule) => {
    const candidates = segments
      .filter((segment) => !used.has(segment) && rule.keywords.some((keyword) => segment.includes(keyword)))
      .sort((a, b) => scoreSegment(b) - scoreSegment(a));
    if (candidates.length === 0) return null;
    used.add(candidates[0]);
    return {
      label: rule.label,
      text: truncateText(candidates[0]),
    };
  }).filter(Boolean);

  if (grouped.length >= 3) return grouped.slice(0, 6);

  const fallbackItems = segments
    .slice()
    .filter((segment) => !used.has(segment))
    .sort((a, b) => scoreSegment(b) - scoreSegment(a))
    .slice(0, 6 - grouped.length)
    .map((segment, index) => ({
      label: `重点 ${index + 1}`,
      text: truncateText(segment),
    }));

  return [...grouped, ...fallbackItems].slice(0, 6);
};

const resolveRecommendedPageCount = ({ charCount, unitCount, signalCount, isUnstructuredLong, maxPages }) => {
  if (charCount === 0) return 1;

  const charPages = Math.ceil(charCount / 520);
  const unitPages = Math.ceil(unitCount / 6);
  const signalPages = Math.ceil(signalCount / 9);
  let recommended = Math.max(1, charPages, unitPages, signalPages);

  // 长段原文通常需要先拆结构，额外给一页空间，但保持建议克制。
  if (isUnstructuredLong) recommended += 1;
  if (charCount <= 320 && unitCount <= 4) recommended = Math.min(recommended, 2);

  const softMax = charCount > 4200 || unitCount > 42 ? 10 : 8;
  return clamp(recommended, 1, Math.min(maxPages, softMax));
};

const resolveRisk = ({ pageCount, recommendedMin, recommendedPageCount }) => {
  if (!pageCount || pageCount >= recommendedMin) {
    return {
      level: 'none',
      message: '',
    };
  }

  const severeThreshold = Math.max(1, Math.floor(recommendedPageCount * 0.55));
  if (pageCount <= severeThreshold) {
    return {
      level: 'high',
      message: `当前 ${pageCount} 页明显低于建议页数，生成时会偏向结论摘要，明细内容容易被压缩或省略。`,
    };
  }

  return {
    level: 'medium',
    message: `当前 ${pageCount} 页低于建议页数，适合做重点版；如需保留更多细节，建议适当增加页数。`,
  };
};

export function analyzeContentCapacity(content, { pageCount = 0, maxPages = 20 } = {}) {
  const text = normalizeText(content);
  const charCount = text.length;
  const lines = unique(text.split('\n').map((line) => line.trim()).filter(Boolean));
  const paragraphs = unique(text.split(/\n\s*\n/).map((item) => item.trim()).filter(Boolean));
  const segments = splitSegments(text);
  const hasListMarkers = lines.some((line) => LIST_MARKER_PATTERN.test(line));
  const lineLikeUnits = hasListMarkers || lines.length >= 5 ? lines : segments;
  const unitCount = lineLikeUnits.length || (charCount > 0 ? 1 : 0);
  const signalCount = countMatches(text, SIGNAL_PATTERN);
  const normalizedMaxPages = Math.max(1, Number(maxPages || 20));
  const normalizedPageCount = Math.max(0, Number(pageCount || 0));
  const isUnstructuredLong = !hasListMarkers && lines.length <= 4 && (charCount >= 600 || (charCount >= 420 && signalCount >= 18));
  const recommendedPageCount = resolveRecommendedPageCount({
    charCount,
    unitCount,
    signalCount,
    isUnstructuredLong,
    maxPages: normalizedMaxPages,
  });
  const recommendedMin = recommendedPageCount >= 4 ? recommendedPageCount - 1 : recommendedPageCount;
  const recommendedMax = recommendedPageCount;
  const risk = resolveRisk({
    pageCount: normalizedPageCount,
    recommendedMin,
    recommendedPageCount,
  });

  return {
    charCount,
    paragraphCount: paragraphs.length,
    unitCount,
    signalCount,
    hasContent: charCount > 0,
    hasListMarkers,
    isUnstructuredLong,
    recommendedPageCount,
    recommendedMin,
    recommendedMax,
    recommendedLabel: recommendedMin === recommendedMax ? `${recommendedMax} 页` : `${recommendedMin}-${recommendedMax} 页`,
    outlineItems: buildOutlineItems(lineLikeUnits),
    riskLevel: risk.level,
    riskMessage: risk.message,
  };
}
