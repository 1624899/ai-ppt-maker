const DEFAULT_JOB_TITLE = '未命名 PPT 任务';
const MAX_TITLE_CHARS = 36;

const HTML_TAG_RE = /<[^>]+>/g;
const HTML_HEADING_RE = /<h[1-3]\b[^>]*>(.*?)<\/h[1-3]>/gis;
const TITLE_LABEL_RE = /^\s*(?:ppt\s*)?(?:标题|题目|主题|名称|title|topic)\s*[:：]\s*/i;
const SECTION_LABEL_RE = /^\s*(?:任务内容|内容|目标受众|受众|风格|页数|要求|摘要|背景|说明|输出|页面|结构)\s*[:：]\s*/i;
const LIST_MARKER_RE = /^\s*(?:[-*•·]+|\d+[.)、]|[一二三四五六七八九十]+[、.])\s*/;

export function normalizeTitleText(value, maxChars = MAX_TITLE_CHARS) {
  const rawText = String(value || '').trim();
  if (!rawText) return '';
  if (looksLikeRichContent(rawText)) {
    return extractMarkupHeading(rawText, maxChars)
      || extractExplicitTitle(rawText, maxChars)
      || extractShortHeadingLine(rawText, maxChars);
  }
  return finalizeTitle(rawText, maxChars);
}

export function deriveTitleFromContent(content, fallback = DEFAULT_JOB_TITLE, maxChars = MAX_TITLE_CHARS) {
  const rawText = String(content || '').trim();
  if (!rawText) return fallback;
  return extractMarkupHeading(rawText, maxChars)
    || extractExplicitTitle(rawText, maxChars)
    || extractShortHeadingLine(rawText, maxChars)
    || fallback;
}

export function resolvePlanTitle(values = [], fallbackContent = '', fallback = DEFAULT_JOB_TITLE) {
  for (const value of values) {
    const title = normalizeTitleText(value);
    if (title) return title;
  }
  return deriveTitleFromContent(fallbackContent, fallback);
}

function extractMarkupHeading(text, maxChars) {
  HTML_HEADING_RE.lastIndex = 0;
  for (const match of text.matchAll(HTML_HEADING_RE)) {
    const heading = finalizeTitle(match[1], maxChars);
    if (heading) return heading;
  }
  return '';
}

function extractExplicitTitle(text, maxChars) {
  for (const rawLine of iterCandidateLines(text)) {
    const line = cleanText(rawLine);
    const matched = line.match(TITLE_LABEL_RE);
    if (!matched) continue;
    return finalizeTitle(line.slice(matched[0].length), maxChars);
  }
  return '';
}

function extractShortHeadingLine(text, maxChars) {
  for (const rawLine of iterCandidateLines(text)) {
    let line = cleanText(rawLine);
    if (!line || TITLE_LABEL_RE.test(line) || SECTION_LABEL_RE.test(line)) continue;
    line = line.replace(LIST_MARKER_RE, '').trim();
    if (looksLikeHeading(line, maxChars)) return finalizeTitle(line, maxChars);
  }
  return '';
}

function iterCandidateLines(text) {
  const htmlNormalized = text.replace(/<\/(?:p|h[1-6]|div|li|br)\s*>/gi, '\n');
  const candidates = htmlNormalized
    .split(/[\r\n]+/)
    .map((line) => line.trim())
    .filter(Boolean);
  return candidates.length > 0 ? candidates.slice(0, 8) : [text];
}

function cleanText(value) {
  return String(value || '')
    .replace(HTML_TAG_RE, ' ')
    .replaceAll('&nbsp;', ' ')
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .trim()
    .split(/\s+/)
    .join(' ');
}

function finalizeTitle(value, maxChars) {
  let text = cleanText(value);
  text = text.replace(TITLE_LABEL_RE, '').replace(SECTION_LABEL_RE, '').trim();
  if (!text) return '';
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars).trimEnd()}...`;
}

function looksLikeRichContent(text) {
  if (/[\r\n]/.test(text)) return true;
  if (/<\/?(?:p|h[1-6]|div|li|br|section|article)\b/i.test(text)) return true;
  return cleanText(text).length > MAX_TITLE_CHARS * 2;
}

function looksLikeHeading(text, maxChars) {
  if (!text || text.length > maxChars) return false;
  if (/[。！？；;]/.test(text)) return false;
  const commaCount = (text.match(/[，,]/g) || []).length;
  return commaCount < 2;
}
