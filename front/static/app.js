const form = document.querySelector("#jobForm");
const pagesGrid = document.querySelector("#pagesGrid");
const submitButton = document.querySelector("#submitButton");
const clearButton = document.querySelector("#clearButton");
const progress = document.querySelector("#progress");
const configText = document.querySelector("#configText");
const modeText = document.querySelector("#modeText");
const jobMeta = document.querySelector("#jobMeta");
const resultLinks = document.querySelector("#resultLinks");
const deliveryResult = document.querySelector("#deliveryResult");
const pageTemplate = document.querySelector("#pageTemplate");
const contentInput = document.querySelector("#content");
const pageCount = document.querySelector("#pageCount");
const imagePreset = document.querySelector("#imagePreset");
const jobTarget = document.querySelector("#jobTarget");
const imageQuality = document.querySelector("#imageQuality");
const pageRichnessDefault = document.querySelector("#pageRichnessDefault");
const pageRichnessList = document.querySelector("#pageRichnessList");
const includeCoverPage = document.querySelector("#includeCoverPage");
const reuseStyleRefsJobId = document.querySelector("#reuseStyleRefsJobId");
const styleImages = document.querySelector("#styleImages");
const styleImagesHint = document.querySelector("#styleImagesHint");
const styleRefGallery = document.querySelector("#styleRefGallery");
const styleNotes = document.querySelector("#styleNotes");
const taskContextCard = document.querySelector("#taskContextCard");
const previewViewer = document.querySelector("#previewViewer");
const thumbList = document.querySelector("#thumbList");
const mainPreviewImage = document.querySelector("#mainPreviewImage");
const mainPreviewCaption = document.querySelector("#mainPreviewCaption");
const stageTimeline = document.querySelector("#stageTimeline");
const historyList = document.querySelector("#historyList");
const newTaskButton = document.querySelector("#newTaskButton");
const interruptButton = document.querySelector("#interruptButton");
const resumeButton = document.querySelector("#resumeButton");
const settingsButton = document.querySelector("#settingsButton");
const settingsDialog = document.querySelector("#settingsDialog");
const closeSettingsButton = document.querySelector("#closeSettingsButton");
const editContentButton = document.querySelector("#editContentButton");
const contentPreviewCard = document.querySelector("#contentPreviewCard");
const contentPreviewTitle = document.querySelector("#contentPreviewTitle");
const contentPreviewText = document.querySelector("#contentPreviewText");
const contentDialog = document.querySelector("#contentDialog");
const contentEditor = document.querySelector("#contentEditor");
const saveContentButton = document.querySelector("#saveContentButton");
const cancelContentButton = document.querySelector("#cancelContentButton");
const closeContentButton = document.querySelector("#closeContentButton");
const modelList = document.querySelector("#modelList");
const modelForm = document.querySelector("#modelForm");
const modelConfigId = document.querySelector("#modelConfigId");
const modelName = document.querySelector("#modelName");
const modelBaseUrl = document.querySelector("#modelBaseUrl");
const modelApiKey = document.querySelector("#modelApiKey");
const modelNameValue = document.querySelector("#modelNameValue");
const modelTemperature = document.querySelector("#modelTemperature");
const modelMaxTokens = document.querySelector("#modelMaxTokens");
const modelOutputFormat = document.querySelector("#modelOutputFormat");
const modelFormMessage = document.querySelector("#modelFormMessage");
const imageLightbox = window.createImageLightbox ? window.createImageLightbox() : null;
const generationResultPresenter = window.PptGenerationResult || null;
const workspaceStatusPresenter = window.PptWorkspaceStatus || null;
const errorLogDialog = window.PptErrorLogDialog || null;

let config = null;
let modelConfigs = null;
let activeModelType = "chat";
let selectedModelId = "";
let isCreatingModel = false;
let currentJob = null;
let currentPreviewPageNo = 1;
let stageOpenState = {};
let jobEventSource = null;
let historyEventSource = null;
let historyItems = [];
let selectedHistoryJobId = "";
let styleReferenceHydrationKey = "";

const pageRichnessHelpers = window.PptPageRichness || null;
const PAGE_RICHNESS_OPTIONS = pageRichnessHelpers?.listOptions?.() || [
  {value: "low", label: "低"},
  {value: "medium", label: "中"},
  {value: "high", label: "高"},
];

imageLightbox?.bindRoot(document);

function formatStageKey(stage) {
  const map = {
    queued: "等待执行",
    planning: "模型规划",
    reference_generation: "参考图生成",
    elements_generation: "元素图生成",
    ppt_export: "PPT 组装",
    completed: "全部完成",
  };
  return map[stage] || "处理中";
}

function normalizeStageLabel(stage) {
  const text = String(stage?.label || "").trim();
  const compact = text.replace(/\s+/g, "");
  const hasCorruptedMarker = /[?？\uFFFD]/.test(compact);
  if (!compact || /^[?？\uFFFD]+$/.test(compact) || (hasCorruptedMarker && compact.length <= 12)) {
    return formatStageKey(stage?.key);
  }
  return text;
}

function updatePresetSummary() {
  if (!config) {
    return;
  }
  const preset = config.image_presets[imagePreset.value] || config.image_presets[config.default_image_preset];
  if (!preset) {
    return;
  }
  configText.textContent = `最多 ${config.max_pages} 页，当前尺寸 ${preset.label}`;
  renderWorkspaceStatus();
}

function summarizeContent(value) {
  const text = String(value || "").trim();
  if (!text) {
    return {
      title: "未填写内容",
      preview: "点击打开二级窗口，粘贴或编辑完整汇报内容。",
    };
  }
  const clean = text.replace(/\s+/g, " ");
  return {
    title: clean.slice(0, 24) + (clean.length > 24 ? "..." : ""),
    preview: clean.slice(0, 120) + (clean.length > 120 ? "..." : ""),
  };
}

function syncContentPreview() {
  const summary = summarizeContent(contentInput.value);
  contentPreviewTitle.textContent = summary.title;
  contentPreviewText.textContent = summary.preview;
  renderWorkspaceStatus();
}

function renderWorkspaceStatus(job = currentJob) {
  if (!workspaceStatusPresenter?.render) {
    return;
  }
  workspaceStatusPresenter.render({
    config,
    job,
    taskContextContainer: taskContextCard,
  });
}

function setJobMetaText(message) {
  if (jobMeta) {
    jobMeta.textContent = message;
  }
}

function buildJobMetaText(job) {
  if (!job?.job_id) {
    return "等待提交任务";
  }
  const pageCount = Number(job.reference_pages?.length || job.job_meta?.page_count || job.pages?.length || 0);
  const targetLabel = String(job.job_meta?.job_target_label || "PPT");
  if (job.status === "completed") {
    return `任务 ${job.job_id} 已完成，共 ${pageCount} 页，可直接下载${targetLabel}`;
  }
  if (job.status === "stopping") {
    return `任务 ${job.job_id} 已暂停，可继续从当前进度恢复`;
  }
  if (job.status === "interrupted") {
    return `任务 ${job.job_id} 已暂停，可继续从当前进度恢复`;
  }
  if (job.status === "error") {
    return `任务 ${job.job_id} 执行失败，请打开错误日志查看详情`;
  }
  return `任务 ${job.job_id} 正在${formatStageKey(job.current_stage || "queued")}`;
}

function showErrorLog(message, options = {}) {
  const safeMessage = String(message || "").trim() || "未提供详细错误信息。";
  errorLogDialog?.open({
    title: options.title || "错误日志",
    subtitle: options.subtitle || "这里集中展示本次失败的详细信息。",
    content: safeMessage,
  });
}

function showJobError(job, fallbackMessage = "") {
  if (!job) {
    showErrorLog(fallbackMessage);
    return;
  }
  errorLogDialog?.openForJob(job, fallbackMessage);
}

function defaultIncludeCoverPageValue() {
  return config?.default_include_cover_page !== false;
}

function defaultPageRichnessValue() {
  return config?.default_page_richness || "medium";
}

function normalizePageRichnessValue(value, fallback = "medium") {
  if (pageRichnessHelpers?.normalizeValue) {
    return pageRichnessHelpers.normalizeValue(value, fallback);
  }
  const normalized = String(value || "").trim().toLowerCase();
  if (PAGE_RICHNESS_OPTIONS.some((item) => item.value === normalized)) {
    return normalized;
  }
  return String(fallback || "medium");
}

function formatPageRichnessText(value, fallback = "medium") {
  if (pageRichnessHelpers?.formatText) {
    return pageRichnessHelpers.formatText(value, fallback);
  }
  return `丰富度 ${normalizePageRichnessValue(value, fallback)}`;
}

function buildPageRichnessMap(pageTotal, sourceMap = {}, defaultValue = defaultPageRichnessValue()) {
  const safeTotal = Math.max(0, Number(pageTotal) || 0);
  const normalizedDefault = normalizePageRichnessValue(defaultValue, "medium");
  const nextMap = {};
  for (let pageNo = 1; pageNo <= safeTotal; pageNo += 1) {
    nextMap[String(pageNo)] = normalizePageRichnessValue(sourceMap?.[String(pageNo)], normalizedDefault);
  }
  return nextMap;
}

function buildPageRichnessState(pageTotal, sourceState = {}, defaultValue = defaultPageRichnessValue()) {
  const safeTotal = Math.max(0, Number(pageTotal) || 0);
  const normalizedDefault = normalizePageRichnessValue(defaultValue, "medium");
  const nextState = {};
  for (let pageNo = 1; pageNo <= safeTotal; pageNo += 1) {
    const rawItem = sourceState?.[String(pageNo)];
    const value =
      rawItem && typeof rawItem === "object"
        ? normalizePageRichnessValue(rawItem.value, normalizedDefault)
        : normalizePageRichnessValue(rawItem, normalizedDefault);
    const customized =
      rawItem && typeof rawItem === "object"
        ? Boolean(rawItem.customized)
        : Object.prototype.hasOwnProperty.call(sourceState || {}, String(pageNo)) && value !== normalizedDefault;
    nextState[String(pageNo)] = {
      value: customized ? value : normalizedDefault,
      customized,
    };
  }
  return nextState;
}

function readCurrentPageRichnessState() {
  const nextState = {};
  if (!pageRichnessList) {
    return nextState;
  }
  pageRichnessList.querySelectorAll("select[data-page-richness-page]").forEach((selectNode) => {
    const pageNo = String(selectNode.dataset.pageRichnessPage || "").trim();
    if (!pageNo) {
      return;
    }
    nextState[pageNo] = {
      value: normalizePageRichnessValue(selectNode.value, defaultPageRichnessValue()),
      customized: selectNode.dataset.pageRichnessCustomized === "1",
    };
  });
  return nextState;
}

function readExplicitPageRichnessMap(defaultValue = defaultPageRichnessValue()) {
  const normalizedDefault = normalizePageRichnessValue(defaultValue, "medium");
  const nextMap = {};
  const currentState = readCurrentPageRichnessState();
  for (const [pageNo, item] of Object.entries(currentState)) {
    if (!item?.customized) {
      continue;
    }
    nextMap[pageNo] = normalizePageRichnessValue(item.value, normalizedDefault);
  }
  return nextMap;
}

function renderPageRichnessControls(pageTotal = Number(pageCount?.value || 0), sourceState = null) {
  if (!pageRichnessList) {
    return;
  }
  const safeTotal = Math.max(0, Number(pageTotal) || 0);
  const defaultValue = normalizePageRichnessValue(pageRichnessDefault?.value, defaultPageRichnessValue());
  const richnessState = buildPageRichnessState(
    safeTotal,
    sourceState || readCurrentPageRichnessState(),
    defaultValue
  );
  pageRichnessList.innerHTML = "";
  for (let pageNo = 1; pageNo <= safeTotal; pageNo += 1) {
    const row = document.createElement("label");
    row.className = "page-richness-row";
    row.innerHTML = `<span>第 ${pageNo} 页</span>`;
    const selectNode = document.createElement("select");
    selectNode.name = `page_richness_${pageNo}`;
    selectNode.dataset.pageRichnessPage = String(pageNo);
    for (const optionItem of PAGE_RICHNESS_OPTIONS) {
      const option = document.createElement("option");
      option.value = optionItem.value;
      option.textContent = optionItem.label;
      option.selected = optionItem.value === richnessState[String(pageNo)]?.value;
      selectNode.appendChild(option);
    }
    selectNode.dataset.pageRichnessCustomized = richnessState[String(pageNo)]?.customized ? "1" : "0";
    selectNode.addEventListener("change", () => {
      const normalizedValue = normalizePageRichnessValue(selectNode.value, defaultValue);
      selectNode.value = normalizedValue;
      selectNode.dataset.pageRichnessCustomized = normalizedValue === defaultValue ? "0" : "1";
    });
    row.appendChild(selectNode);
    pageRichnessList.appendChild(row);
  }
}

function formatStyleImageHint(message) {
  if (styleImagesHint) {
    styleImagesHint.textContent = message;
  }
}

function clearStyleReferenceBinding() {
  styleReferenceHydrationKey = "";
  styleImages.value = "";
  if (reuseStyleRefsJobId) {
    reuseStyleRefsJobId.value = "";
  }
  if (styleRefGallery) {
    styleRefGallery.hidden = true;
    styleRefGallery.innerHTML = "";
  }
  formatStyleImageHint("支持查看历史任务时自动回填参考图；也可以重新选择本地文件覆盖。");
}

function renderStyleReferenceGallery(items, sourceLabel = "") {
  if (!styleRefGallery) {
    return;
  }
  const safeItems = Array.isArray(items) ? items.filter((item) => item?.url) : [];
  if (!safeItems.length) {
    styleRefGallery.hidden = true;
    styleRefGallery.innerHTML = "";
    return;
  }
  styleRefGallery.hidden = false;
  styleRefGallery.innerHTML = safeItems
    .map((item) => {
      return `
        <figure class="style-ref-card">
          <img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.name || "参考风格图")}" />
          <figcaption>${escapeHtml(item.name || "参考风格图")}</figcaption>
        </figure>
      `;
    })
    .join("");
  const sourceText = sourceLabel ? `${sourceLabel}，` : "";
  formatStyleImageHint(`${sourceText}当前共绑定 ${safeItems.length} 张参考风格图；你也可以重新选择本地文件覆盖。`);
}

function getStyleReferenceImages(job) {
  const items = job?.job_meta?.style_reference_images;
  return Array.isArray(items) ? items : [];
}

function buildStyleReferenceHydrationKey(job) {
  const items = getStyleReferenceImages(job);
  const itemNames = items.map((item) => `${item.name || ""}:${item.url || ""}`).join("|");
  return `${job?.job_id || ""}::${itemNames}`;
}

async function buildFileFromStyleReference(item, index) {
  const res = await fetch(item.url);
  if (!res.ok) {
    throw new Error(`读取参考图失败：${item.name || item.url}`);
  }
  const blob = await res.blob();
  const fileName = String(item.name || `style_ref_${index + 1}.png`);
  const mimeType = blob.type || "image/png";
  return new File([blob], fileName, {type: mimeType, lastModified: Date.now()});
}

async function hydrateStyleImagesFromJob(job) {
  const items = getStyleReferenceImages(job);
  const hydrationKey = buildStyleReferenceHydrationKey(job);
  if (!items.length) {
    clearStyleReferenceBinding();
    return;
  }
  if (reuseStyleRefsJobId) {
    reuseStyleRefsJobId.value = String(job?.job_id || "");
  }
  renderStyleReferenceGallery(items, "已回填历史任务参考图");
  if (styleReferenceHydrationKey === hydrationKey) {
    return;
  }
  styleReferenceHydrationKey = hydrationKey;
  try {
    const files = await Promise.all(items.map(buildFileFromStyleReference));
    const transfer = new DataTransfer();
    for (const file of files) {
      transfer.items.add(file);
    }
    styleImages.files = transfer.files;
    formatStyleImageHint(`已自动回填 ${files.length} 张历史参考图，重新提交任务时会继续使用这些文件。`);
  } catch (error) {
    formatStyleImageHint(`已展示历史参考图预览，但浏览器未能写回文件选择器：${error.message}`);
  }
}

function resetFormToDefaults() {
  if (!config) {
    return;
  }
  contentInput.value = "";
  contentEditor.value = "";
  pageCount.value = String(config.default_pages);
  imagePreset.value = config.default_image_preset;
  jobTarget.value = "editable_ppt";
  imageQuality.value = config.image_quality || "medium";
  pageRichnessDefault.value = defaultPageRichnessValue();
  includeCoverPage.checked = defaultIncludeCoverPageValue();
  styleNotes.value = "";
  clearStyleReferenceBinding();
  renderPageRichnessControls(Number(pageCount.value || config.default_pages), {});
  syncContentPreview();
  updatePresetSummary();
}

function applyJobParamsToForm(job, historyItem = null) {
  const meta = job?.job_meta || {};
  const nextContent = String(meta.content || "");
  const nextPageCount = Number(meta.page_count || historyItem?.page_count || pageCount.value || 1);
  const nextPresetName = String(meta.image_preset?.name || historyItem?.image_preset || imagePreset.value || "");
  const nextQuality = String(meta.image_quality || historyItem?.image_quality || imageQuality.value || "medium");
  const nextJobTarget = String(meta.job_target || historyItem?.job_target || jobTarget.value || "editable_ppt");
  const nextStyleNotes = String(meta.style_notes || historyItem?.style_notes || "");
  const nextIncludeCoverPage =
    meta.generation_options?.include_cover_page ?? defaultIncludeCoverPageValue();
  const nextPageRichnessDefault = normalizePageRichnessValue(
    meta.generation_options?.page_richness_default,
    defaultPageRichnessValue()
  );
  const nextPageRichnessMap = meta.generation_options?.page_richness_map || {};

  contentInput.value = nextContent;
  pageCount.value = String(nextPageCount);
  if (nextPresetName && [...imagePreset.options].some((option) => option.value === nextPresetName)) {
    imagePreset.value = nextPresetName;
  }
  if (nextQuality && [...imageQuality.options].some((option) => option.value === nextQuality)) {
    imageQuality.value = nextQuality;
  }
  if (nextJobTarget && [...jobTarget.options].some((option) => option.value === nextJobTarget)) {
    jobTarget.value = nextJobTarget;
  }
  pageRichnessDefault.value = nextPageRichnessDefault;
  includeCoverPage.checked = Boolean(nextIncludeCoverPage);
  styleNotes.value = nextStyleNotes;
  renderPageRichnessControls(nextPageCount, nextPageRichnessMap);
  syncContentPreview();
  updatePresetSummary();
}

function openContentDialog() {
  contentEditor.value = contentInput.value;
  contentDialog.showModal();
  window.setTimeout(() => contentEditor.focus(), 0);
}

function closeContentDialog() {
  contentDialog.close();
}

function saveContentDraft() {
  contentInput.value = contentEditor.value;
  syncContentPreview();
  closeContentDialog();
}

async function loadConfig() {
  const res = await fetch("/api/config");
  config = await res.json();
  pageCount.max = config.max_pages;
  pageCount.value = config.default_pages;
  imagePreset.innerHTML = "";
  for (const [value, preset] of Object.entries(config.image_presets)) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = preset.label;
    option.selected = value === config.default_image_preset;
    imagePreset.appendChild(option);
  }
  imageQuality.value = config.image_quality || "medium";
  pageRichnessDefault.value = defaultPageRichnessValue();
  renderPageRichnessControls(Number(pageCount.value || config.default_pages), {});
  updatePresetSummary();
  renderWorkspaceStatus(null);
  await loadModelConfigs();
  await loadJobHistory();
  startHistoryStream();
  updateModeText();
}

async function loadJobHistory() {
  const res = await fetch("/api/jobs");
  const data = await res.json();
  historyItems = data.items || [];
  renderHistoryList();
  if (!selectedHistoryJobId && historyItems.length) {
    selectHistoryJob(historyItems[0].job_id);
  }
}

function startHistoryStream() {
  if (historyEventSource) {
    historyEventSource.close();
  }
  historyEventSource = new EventSource("/api/jobs/stream");
  historyEventSource.addEventListener("history", (event) => {
    const data = JSON.parse(event.data);
    historyItems = data.items || [];
    if (selectedHistoryJobId && !historyItems.some((item) => item.job_id === selectedHistoryJobId)) {
      selectedHistoryJobId = "";
      if (currentJob && !historyItems.some((item) => item.job_id === currentJob.job_id)) {
        currentJob = null;
      }
    }
    renderHistoryList();
  });
}

async function loadModelConfigs() {
  const res = await fetch("/api/model-configs");
  modelConfigs = await res.json();
}

function updateModeText() {
  if (!modelConfigs) {
    modeText.textContent = `${config.generation_mode} · ${config.image_model}`;
    return;
  }
  const chat = findActiveConfig("chat");
  const image = findActiveConfig("image");
  modeText.textContent = `${chat?.model || "chat"} → ${image?.model || "image"} · ${config.image_size}`;
}

function findActiveConfig(type) {
  const activeId = modelConfigs[`active_${type}_config_id`];
  return modelConfigs.configs[type].find((item) => item.id === activeId) || modelConfigs.configs[type][0];
}

function currentModelItems() {
  return modelConfigs?.configs?.[activeModelType] || [];
}

function updateSubmitButtonState() {
  const status = currentJob?.status || "";
  const target = currentJob?.job_meta?.job_target || jobTarget?.value || "editable_ppt";
  let label = target === "reference_only" ? "生成图片版 PPT" : "生成可编辑 PPT";
  if (status === "stopping") {
    label = "任务已暂停";
  } else if (status === "interrupted") {
    label = "任务已暂停";
  } else if (status === "queued" || status === "running") {
    label = "生成中...";
  }
  submitButton.querySelector("span:last-child").textContent = label;
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  progress.classList.toggle("is-active", isLoading);
  updateSubmitButtonState();
  syncJobActionButtons();
}

function resetWorkspaceView(message = "等待提交任务") {
  stopJobStream();
  currentJob = null;
  selectedHistoryJobId = "";
  pagesGrid.innerHTML = "";
  thumbList.innerHTML = "";
  stageTimeline.innerHTML = "";
  previewViewer.classList.remove("is-active");
  mainPreviewImage.removeAttribute("src");
  mainPreviewImage.hidden = false;
  const figure = previewViewer.querySelector(".main-preview");
  figure.classList.remove("is-placeholder");
  const placeholder = figure.querySelector(".main-preview-placeholder");
  if (placeholder) {
    placeholder.remove();
  }
  mainPreviewCaption.textContent = "等待生成";
  setJobMetaText(message);
  if (resultLinks) {
    resultLinks.innerHTML = "";
    resultLinks.hidden = true;
  }
  if (deliveryResult) {
    deliveryResult.innerHTML = "";
  }
  stageOpenState = {};
  setLoading(false);
  syncJobActionButtons();
  renderHistoryList();
  renderWorkspaceStatus(null);
}

function startNewTask(openEditor = false) {
  resetWorkspaceView("已切换到新任务");
  resetFormToDefaults();
  if (openEditor) {
    openContentDialog();
    return;
  }
  contentPreviewCard.focus();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

function buildLightboxAttributes(src, alt, caption) {
  const safeSrc = String(src || "").trim();
  if (!safeSrc) {
    return "";
  }
  return [
    'class="lightbox-trigger"',
    `data-lightbox-src="${escapeHtml(safeSrc)}"`,
    `data-lightbox-alt="${escapeHtml(alt || caption || "放大预览")}"`,
    `data-lightbox-caption="${escapeHtml(caption || alt || "")}"`,
    'title="点击放大预览"',
  ].join(" ");
}

function applyLightboxTarget(node, src, alt, caption) {
  if (!node) {
    return;
  }

  const safeSrc = String(src || "").trim();
  if (!safeSrc) {
    node.classList.remove("lightbox-trigger");
    node.removeAttribute("data-lightbox-src");
    node.removeAttribute("data-lightbox-alt");
    node.removeAttribute("data-lightbox-caption");
    node.removeAttribute("title");
    return;
  }

  node.classList.add("lightbox-trigger");
  node.dataset.lightboxSrc = safeSrc;
  node.dataset.lightboxAlt = String(alt || caption || "放大预览");
  node.dataset.lightboxCaption = String(caption || alt || "");
  node.title = "点击放大预览";
}

function getStageStatusLabel(status) {
  const map = {
    pending: "等待中",
    queued: "排队中",
    running: "进行中",
    stopping: "已暂停",
    interrupted: "已暂停",
    skipped: "已跳过",
    completed: "已完成",
    error: "失败",
  };
  return map[status] || "处理中";
}

function getPageStatusLabel(status) {
  const map = {
    pending: "等待规划",
    planned: "已完成规划",
    rendering_reference: "参考图生成中",
    reference_done: "参考图已完成",
    rendering_elements: "元素图生成中",
    completed: "全部完成",
  };
  return map[status] || "处理中";
}

function currentStageLabel(job) {
  const labels = {
    queued: "任务已创建，等待执行",
    planning: "正在进行模型规划",
    reference_generation: "正在生成带文字参考图",
    elements_generation: "正在生成去文字元素图",
    ppt_export: "正在执行图像后处理并导出 PPTX",
    completed: "全部阶段已完成",
  };
  if (job.status === "stopping") {
    return "任务已暂停，可点击继续从当前进度恢复";
  }
  if (job.status === "interrupted") {
    return "任务已暂停，可点击继续从当前进度恢复";
  }
  if (job.status === "error") {
    return `任务失败：${job.error || "请查看阶段日志"}`;
  }
  if (job.status === "completed" && job.job_meta?.job_target === "reference_only") {
    return "参考图与图片版 PPT 已完成";
  }
  return labels[job.current_stage] || "任务运行中";
}

function renderResultLinks(job) {
  if (!resultLinks) {
    return;
  }
  const exportResult = job?.result?.export || {};
  const links = [];
  if (exportResult.pptx_url) {
    links.push(`<a href="${escapeHtml(exportResult.pptx_url)}" target="_blank" rel="noreferrer">下载 PPTX</a>`);
  }
  if (exportResult.project_url) {
    links.push(`<a href="${escapeHtml(exportResult.project_url)}" target="_blank" rel="noreferrer">查看项目快照</a>`);
  }
  resultLinks.hidden = links.length === 0;
  resultLinks.innerHTML = links.join(" · ");
}

function renderGenerationResult(job) {
  if (generationResultPresenter?.render && deliveryResult) {
    generationResultPresenter.render({
      container: deliveryResult,
      linksContainer: resultLinks,
      job,
    });
    return;
  }
  renderResultLinks(job);
}

function syncStyleReferenceSelectionHint() {
  const fileCount = styleImages?.files?.length || 0;
  if (!fileCount) {
    return;
  }
  if (styleRefGallery) {
    styleRefGallery.hidden = true;
    styleRefGallery.innerHTML = "";
  }
  styleReferenceHydrationKey = "";
  if (reuseStyleRefsJobId) {
    reuseStyleRefsJobId.value = "";
  }
  formatStyleImageHint(`当前已选择 ${fileCount} 张本地参考图，提交任务时会以上传内容为准。`);
}

function findPreviewPage(job) {
  if (!job?.pages?.length) {
    return null;
  }
  const selected = job.pages.find((page) => Number(page.page_no) === Number(currentPreviewPageNo));
  if (selected) {
    return selected;
  }
  const withImage = job.pages.find((page) => page.reference_image) || job.pages[0];
  currentPreviewPageNo = withImage?.page_no || 1;
  return withImage;
}

function setMainPreviewImage(src, caption) {
  previewViewer.classList.add("is-active");
  mainPreviewImage.hidden = false;
  mainPreviewImage.src = src;
  applyLightboxTarget(mainPreviewImage, src, "PPT 主预览", caption);
  mainPreviewCaption.textContent = caption;
  const figure = previewViewer.querySelector(".main-preview");
  figure.classList.remove("is-placeholder");
  const placeholder = figure.querySelector(".main-preview-placeholder");
  if (placeholder) {
    placeholder.remove();
  }
}

function buildGlassSlide(title, caption) {
  return `
    <div class="glass-slide">
      <div class="glass-slide-inner">
        <div class="glass-line is-title"></div>
        <div class="glass-line is-wide"></div>
        <div class="glass-grid">
          <div class="glass-box"></div>
          <div class="glass-box is-stack">
            <div class="glass-line is-mid"></div>
            <div class="glass-line is-wide"></div>
            <div class="glass-line is-mid"></div>
          </div>
        </div>
        <div class="glass-caption">${escapeHtml(title || "正在生成当前页")}</div>
        <div class="glass-caption">${escapeHtml(caption || "图片完成后会自动替换到这里")}</div>
      </div>
    </div>
  `;
}

function setMainPreviewPlaceholder(page, job) {
  previewViewer.classList.add("is-active");
  mainPreviewImage.hidden = true;
  mainPreviewImage.removeAttribute("src");
  applyLightboxTarget(mainPreviewImage, "", "", "");
  const figure = previewViewer.querySelector(".main-preview");
  figure.classList.add("is-placeholder");
  let placeholder = figure.querySelector(".main-preview-placeholder");
  if (!placeholder) {
    placeholder = document.createElement("div");
    placeholder.className = "main-preview-placeholder";
    figure.prepend(placeholder);
  }
  const stageLabel = currentStageLabel(job);
  placeholder.innerHTML = `
    <div class="main-preview-stage">${escapeHtml(stageLabel)}</div>
    ${buildGlassSlide(page?.title || "正在生成当前页", "毛玻璃占位预览")}
  `;
  mainPreviewCaption.textContent = page ? `第 ${page.page_no} 页 · ${page.title}` : "等待生成";
}

function renderPreviewViewer(job) {
  thumbList.innerHTML = "";
  const pages = job.pages || [];
  if (!pages.length) {
    previewViewer.classList.remove("is-active");
    return;
  }
  previewViewer.classList.add("is-active");
  const activePage = findPreviewPage(job);
  if (activePage?.reference_image) {
    setMainPreviewImage(activePage.reference_image, `第 ${activePage.page_no} 页 · ${activePage.title}`);
  } else {
    setMainPreviewPlaceholder(activePage, job);
  }

  for (const page of pages) {
    const button = document.createElement("button");
    button.className = "thumb-button";
    button.type = "button";
    if (Number(page.page_no) === Number(currentPreviewPageNo)) {
      button.classList.add("is-active");
    }
    if (page.reference_image) {
      button.innerHTML = `<img src="${page.reference_image}" alt="第 ${page.page_no} 页缩略图" />`;
    } else {
      button.classList.add("is-placeholder");
      button.innerHTML = buildGlassSlide(`第 ${page.page_no} 页`, getPageStatusLabel(page.status));
    }
    button.addEventListener("click", () => {
      currentPreviewPageNo = page.page_no;
      renderPreviewViewer(job);
    });
    thumbList.appendChild(button);
  }
}

function renderFinalPages(job) {
  pagesGrid.innerHTML = "";
  if (!job.reference_pages?.length) {
    return;
  }
  for (const ref of job.reference_pages) {
    const element = job.element_pages.find((item) => item.page_no === ref.page_no) || {};
    const pageData = (job.pages || []).find((p) => p.page_no === ref.page_no) || {};
    const node = pageTemplate.content.cloneNode(true);
    node.querySelector("h3").textContent = ref.title;
    node.querySelector(".page-card-head span").textContent = `第 ${ref.page_no} 页`;
    const layoutTag = node.querySelector(".layout-tag");
    const modeTag = node.querySelector(".mode-tag");
    const profileTag = node.querySelector(".profile-tag");
    if (layoutTag && pageData.layout_family) {
      layoutTag.textContent = pageData.layout_family;
    } else if (layoutTag) {
      layoutTag.remove();
    }
    if (modeTag && pageData.reference_mode) {
      modeTag.textContent = pageData.reference_mode;
    } else if (modeTag) {
      modeTag.remove();
    }
    if (profileTag && pageData.prompt_profile) {
      profileTag.textContent = pageData.prompt_profile;
    } else if (profileTag) {
      profileTag.remove();
    }
    const imgs = node.querySelectorAll("img");
    imgs[0].src = ref.image;
    imgs[1].src = element.image || ref.image;
    applyLightboxTarget(imgs[0], ref.image, "带文字 PPT 参考图", `第 ${ref.page_no} 页 · ${ref.title} · 带文字参考图`);
    applyLightboxTarget(
      imgs[1],
      element.image || ref.image,
      "去文字元素图",
      `第 ${ref.page_no} 页 · ${ref.title} · 去文字元素图`
    );
    node.querySelector("pre").textContent = ref.prompt;
    pagesGrid.appendChild(node);
  }
}

function renderGrammarPanel(styleGuide) {
  if (!styleGuide) {
    return "";
  }
  const core = styleGuide.style_core || {};
  const coreHtml = Object.entries(core)
    .map(([key, val]) => {
      const display = Array.isArray(val) ? val.join("、") : String(val);
      return `<div class="grammar-row"><span class="grammar-key">${escapeHtml(key)}</span><span class="grammar-val">${escapeHtml(display)}</span></div>`;
    })
    .join("");
  const families = (styleGuide.layout_families || []).map((f) => `<li>${escapeHtml(f)}</li>`).join("");
  const primitives = (styleGuide.element_primitives || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
  const negatives = (styleGuide.negative_rules || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("");
  const anchor = styleGuide.prompt_anchor || "";
  const compression = styleGuide.prompt_compression || "";

  return `
    <details class="grammar-panel">
      <summary class="grammar-summary">风格 Grammar</summary>
      <div class="grammar-body">
        ${coreHtml ? `<div class="grammar-section"><h5>style_core</h5>${coreHtml}</div>` : ""}
        ${families ? `<div class="grammar-section"><h5>layout_families</h5><ul class="grammar-list">${families}</ul></div>` : ""}
        ${primitives ? `<div class="grammar-section"><h5>element_primitives</h5><ul class="grammar-list">${primitives}</ul></div>` : ""}
        ${negatives ? `<div class="grammar-section"><h5>negative_rules</h5><ul class="grammar-list">${negatives}</ul></div>` : ""}
        ${anchor ? `<div class="grammar-section"><h5>prompt_anchor</h5><p class="grammar-anchor">${escapeHtml(anchor)}</p></div>` : ""}
        ${compression ? `<div class="grammar-section"><h5>prompt_compression</h5><p class="grammar-compression">${escapeHtml(compression)}</p></div>` : ""}
      </div>
    </details>
  `;
}

function renderEvaluationSummary(evaluation) {
  if (!evaluation) {
    return "";
  }
  const scoreClass = evaluation.overall_score >= 0.7 ? "is-passed" : "is-failed";
  const pageScores = (evaluation.page_scores || [])
    .map((ps) => {
      const cls = ps.passed ? "is-passed" : "is-failed";
      const issuesTip = (ps.issues || []).join("; ");
      return `<span class="eval-page-score ${cls}" title="${escapeHtml(issuesTip)}">P${ps.page_no}: ${ps.score.toFixed(2)}</span>`;
    })
    .join("");
  return `
    <div class="evaluation-summary">
      <span class="eval-overall ${scoreClass}">整体评分：${evaluation.overall_score.toFixed(2)}</span>
      <span class="eval-detail">${escapeHtml(evaluation.summary || "")}</span>
      ${pageScores ? `<div class="eval-page-scores">${pageScores}</div>` : ""}
    </div>
  `;
}

function renderPlanningStage(stage) {
  const data = stage.data || {};
  const pages = data.pages || [];
  if (!pages.length) {
    return "";
  }
  return `
    <div class="plan-meta">
      <div class="meta-card">
        <span>风格类型</span>
        <strong>${escapeHtml(data.style_type || "待识别")}</strong>
      </div>
      <div class="meta-card">
        <span>目标受众</span>
        <strong>${escapeHtml(data.audience || "待生成")}</strong>
      </div>
      <div class="meta-card">
        <span>叙事线</span>
        <strong>${escapeHtml(data.narrative || "待生成")}</strong>
      </div>
    </div>
    ${renderGrammarPanel(data.style_guide)}
    ${renderEvaluationSummary(data.evaluation)}
    <div class="plan-pages">
      ${pages
        .map(
          (page) => `
            <article class="plan-page-card">
              <h4>第 ${page.page_no} 页 · ${escapeHtml(page.title)}</h4>
              ${renderPageMetaTags(page)}
              ${renderPageElementPlan(page)}
              ${renderPageEvaluationBadge(page)}
              <p>${escapeHtml(page.summary || "暂无摘要")}</p>
              ${
                page.bullets?.length
                  ? `<ul>${page.bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("")}</ul>`
                  : ""
              }
              <pre>${escapeHtml(page.image_prompt || "")}</pre>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function renderPageMetaTags(page) {
  const parts = [];
  if (page.layout_family) {
    parts.push(`<span class="meta-tag layout-tag">${escapeHtml(page.layout_family)}</span>`);
  }
  if (page.page_richness) {
    parts.push(`<span class="meta-tag richness-tag">${escapeHtml(formatPageRichnessText(page.page_richness))}</span>`);
  }
  if (page.reference_mode) {
    parts.push(`<span class="meta-tag mode-tag">${escapeHtml(page.reference_mode)}</span>`);
  }
  if (page.prompt_profile) {
    parts.push(`<span class="meta-tag profile-tag">${escapeHtml(page.prompt_profile)}</span>`);
  }
  if (!parts.length) {
    return "";
  }
  return `<div class="page-meta-tags">${parts.join("")}</div>`;
}

function renderPageElementPlan(page) {
  const primitives = page.element_plan?.primitives || page.element_primitives || [];
  if (!primitives.length) {
    return "";
  }
  return `<div class="page-element-plan"><span class="element-plan-label">primitives：</span>${primitives.map((p) => `<span class="element-primitive-tag">${escapeHtml(p)}</span>`).join("")}</div>`;
}

function renderPageEvaluationBadge(page) {
  const evaluation = page.evaluation;
  if (!evaluation) {
    return "";
  }
  const scoreClass = evaluation.passed ? "is-passed" : "is-failed";
  const scoreText = typeof evaluation.score === "number" ? evaluation.score.toFixed(2) : "-";
  return `<span class="page-eval-badge ${scoreClass}" title="${escapeHtml((evaluation.issues || []).join("; "))}">评估 ${scoreText}</span>`;
}

function renderGenerationStage(stage, job, imageKey) {
  const pages = job.pages || [];
  return `
    <div class="stage-page-list">
      ${pages
        .map((page) => {
          const image = imageKey === "reference_image" ? page.reference_image : page.element_image;
          const prompt = imageKey === "reference_image" ? page.reference_prompt : page.elements_prompt;
          return `
            <article class="stage-page-card">
              <div class="stage-page-head">
                <h4>第 ${page.page_no} 页 · ${escapeHtml(page.title)}</h4>
                <span class="page-mini-status">${escapeHtml(getPageStatusLabel(page.status))}</span>
                ${renderPageEvaluationBadge(page)}
              </div>
              ${renderPageMetaTags(page)}
              ${renderPageElementPlan(page)}
              ${
                image
                  ? `<img src="${image}" alt="第 ${page.page_no} 页预览" ${buildLightboxAttributes(image, `第 ${page.page_no} 页预览`, `第 ${page.page_no} 页 · ${page.title}`)} />`
                  : buildGlassSlide(page.title, getPageStatusLabel(page.status))
              }
              ${prompt ? `<pre>${escapeHtml(prompt)}</pre>` : ""}
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderStageBody(stage, job) {
  const logs = stage.logs?.length
    ? `<ul class="stage-logs">${stage.logs.map((log) => `<li>${escapeHtml(log)}</li>`).join("")}</ul>`
    : "";
  let extra = "";
  if (stage.key === "planning") {
    extra = renderPlanningStage(stage);
  } else if (stage.key === "reference_generation") {
    extra = renderGenerationStage(stage, job, "reference_image");
  } else if (stage.key === "elements_generation") {
    extra = renderGenerationStage(stage, job, "element_image");
  }
  return `<div class="stage-body">${logs}${extra}</div>`;
}

function renderStageTimeline(job) {
  stageTimeline.innerHTML = "";
  const stages = job.stages || [];
  for (const stage of stages) {
    const details = document.createElement("details");
    details.className = "stage-card";
    const shouldOpen = Object.prototype.hasOwnProperty.call(stageOpenState, stage.key)
      ? stageOpenState[stage.key]
      : stage.status !== "completed";
    details.open = shouldOpen;
    details.innerHTML = `
      <summary class="stage-summary">
        <div class="stage-summary-main">
          <div class="stage-summary-top">
            <h3>${escapeHtml(normalizeStageLabel(stage))}</h3>
            <span class="stage-status is-${escapeHtml(stage.status)}">${escapeHtml(getStageStatusLabel(stage.status))}</span>
          </div>
          <p>${escapeHtml(stage.summary || "")}</p>
        </div>
      </summary>
      ${renderStageBody(stage, job)}
    `;
    details.addEventListener("toggle", () => {
      stageOpenState[stage.key] = details.open;
    });
    stageTimeline.appendChild(details);
  }
}

function renderJob(job) {
  const previousStatus = currentJob?.status || "";
  currentJob = job;
  selectedHistoryJobId = job.job_id;
  syncHistoryItemFromJob(job);
  applyJobParamsToForm(job, historyItems.find((item) => item.job_id === job.job_id) || null);
  renderStageTimeline(job);
  renderPreviewViewer(job);
  renderFinalPages(job);
  renderGenerationResult(job);
  setJobMetaText(buildJobMetaText(job));
  if (job.status === "error" && ["queued", "running", "stopping"].includes(previousStatus)) {
    showJobError(job);
  }
  syncJobActionButtons();
  renderHistoryList();
  renderWorkspaceStatus(job);
}

function syncHistoryItemFromJob(job) {
  if (!job?.job_id) {
    return;
  }
  const index = historyItems.findIndex((item) => item.job_id === job.job_id);
  const existing = index >= 0 ? historyItems[index] : {};
  const preset = job.job_meta?.image_preset || {};
  const nextItem = {
    job_id: job.job_id,
    title: existing.title || summarizeContent(job.job_meta?.content || "").title || job.job_id,
    status: job.status || existing.status || "queued",
    current_stage: job.current_stage || existing.current_stage || "queued",
    page_count: job.job_meta?.page_count || job.pages?.length || existing.page_count || 0,
    image_preset: preset.label || preset.name || existing.image_preset || "",
    image_quality: job.job_meta?.image_quality || existing.image_quality || "",
    job_target: job.job_meta?.job_target || existing.job_target || "editable_ppt",
    style_notes: job.job_meta?.style_notes || existing.style_notes || "",
    generation_options: job.job_meta?.generation_options || existing.generation_options || {},
    created_at: existing.created_at || "",
    updated_at: new Date().toISOString(),
    stop_requested: Boolean(job.stop_requested),
    preview_image:
      job.pages?.find((page) => page.reference_image)?.reference_image ||
      existing.preview_image ||
      "",
  };
  if (index >= 0) {
    historyItems[index] = nextItem;
  } else {
    historyItems.unshift(nextItem);
  }
}

function renderHistoryList() {
  if (!historyList) {
    return;
  }
  newTaskButton?.classList.toggle("is-active", !selectedHistoryJobId && !currentJob);
  historyList.innerHTML = "";
  if (!historyItems.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.innerHTML = `
      <div class="history-empty-icon">⌘</div>
      <h3>暂无任务</h3>
      <p>创建后会自动保存到这里，方便回看参数、继续生成和删除任务记录。</p>
    `;
    historyList.appendChild(empty);
    return;
  }
  for (const item of historyItems) {
    const article = document.createElement("article");
    article.className = `history-item${item.job_id === selectedHistoryJobId ? " is-active" : ""}`;
    const preview = item.preview_image
      ? `<img class="history-cover" src="${item.preview_image}" alt="任务预览" />`
      : `<div class="history-cover is-placeholder"><span>${escapeHtml(item.page_count || 0)} 页</span></div>`;
    article.innerHTML = `
      <button class="history-item-main" type="button">
        <div class="history-cover-wrap">${preview}</div>
        <div class="history-item-head">
          <h3>${escapeHtml(item.title || item.job_id)}</h3>
          <span class="stage-status is-${escapeHtml(item.status)}">${escapeHtml(getStageStatusLabel(item.status))}</span>
        </div>
        <p>${escapeHtml(item.image_preset)} · ${escapeHtml(item.image_quality)} · ${item.page_count} 页</p>
        <div class="history-meta">
          <span>${escapeHtml(formatStageKey(item.current_stage || "queued"))}</span>
          <span>${escapeHtml((item.updated_at || "").replace("T", " ").slice(0, 16))}</span>
        </div>
      </button>
      <div class="history-item-actions">
        <button class="mini-button danger-button" type="button" data-action="delete">删除</button>
      </div>
    `;
    article.querySelector(".history-item-main").addEventListener("click", () => selectHistoryJob(item.job_id));
    article.querySelector('[data-action="delete"]').addEventListener("click", (event) => {
      event.stopPropagation();
      deleteHistoryJob(item.job_id);
    });
    historyList.appendChild(article);
  }
}

async function selectHistoryJob(jobId) {
  selectedHistoryJobId = jobId;
  renderHistoryList();
  stopJobStream();
  const selectedItem = historyItems.find((item) => item.job_id === jobId) || null;
  const res = await fetch(`/api/jobs/${jobId}`);
  const data = await res.json();
  if (!res.ok) {
    setJobMetaText("读取任务失败，请查看错误日志");
    showErrorLog(data.error || "读取任务失败", {
      title: "读取任务失败",
      subtitle: `任务 ID：${jobId}`,
    });
    return;
  }
  applyJobParamsToForm(data, selectedItem);
  await hydrateStyleImagesFromJob(data);
  renderJob(data);
  if (data.status === "queued" || data.status === "running" || data.status === "stopping") {
    setLoading(true);
    startJobStream(jobId);
  } else {
    setLoading(false);
  }
}

function syncJobActionButtons() {
  const status = currentJob?.status || "";
  interruptButton.disabled = !["queued", "running"].includes(status);
  const canUpgradeReferenceOnly =
    status === "completed" && currentJob?.job_meta?.job_target === "reference_only";
  resumeButton.disabled = !(["interrupted", "error"].includes(status) || canUpgradeReferenceOnly);
  resumeButton.textContent = canUpgradeReferenceOnly ? "继续转可编辑" : "继续生成";
}

function stopJobStream() {
  if (jobEventSource) {
    jobEventSource.close();
    jobEventSource = null;
  }
}

function startJobStream(jobId) {
  stopJobStream();
  jobEventSource = new EventSource(`/api/jobs/${jobId}/stream`);
  jobEventSource.addEventListener("job", (event) => {
    const data = JSON.parse(event.data);
    renderJob(data);
    if (["queued", "running", "stopping"].includes(data.status)) {
      setLoading(true);
      return;
    }
    setLoading(false);
    stopJobStream();
  });
  jobEventSource.addEventListener("error", () => {
    if (currentJob?.job_id === jobId && ["queued", "running", "stopping"].includes(currentJob?.status || "")) {
      setJobMetaText("任务状态流已断开，正在等待重新连接...");
    }
  });
}

async function deleteHistoryJob(jobId) {
  if (!window.confirm("确定删除这条任务吗？")) {
    return;
  }
  const res = await fetch(`/api/jobs/${jobId}`, {method: "DELETE"});
  const data = await res.json();
  if (!res.ok) {
    setJobMetaText("删除任务失败，请查看错误日志");
    showErrorLog(data.error || "删除任务失败", {
      title: "删除任务失败",
      subtitle: `任务 ID：${jobId}`,
    });
    return;
  }
  if (selectedHistoryJobId === jobId) {
    stopJobStream();
    currentJob = null;
    selectedHistoryJobId = "";
    pagesGrid.innerHTML = "";
    thumbList.innerHTML = "";
    stageTimeline.innerHTML = "";
    previewViewer.classList.remove("is-active");
    mainPreviewImage.removeAttribute("src");
    mainPreviewCaption.textContent = "等待生成";
    setJobMetaText("该任务已删除");
    if (resultLinks) {
      resultLinks.innerHTML = "";
      resultLinks.hidden = true;
    }
    setLoading(false);
    syncJobActionButtons();
    renderWorkspaceStatus(null);
  }
}

async function interruptCurrentJob() {
  if (!currentJob?.job_id) {
    return;
  }
  const res = await fetch(`/api/jobs/${currentJob.job_id}/interrupt`, {method: "POST"});
  const data = await res.json();
  if (!res.ok) {
    setJobMetaText("停止任务失败，请查看错误日志");
    showErrorLog(data.error || "停止任务失败", {
      title: "停止任务失败",
      subtitle: `任务 ID：${currentJob.job_id}`,
    });
    return;
  }
  currentJob = {...currentJob, status: "interrupted"};
  setJobMetaText("任务已暂停，可点击继续从当前进度恢复。");
  syncJobActionButtons();
  startJobStream(currentJob.job_id);
}

async function resumeCurrentJob() {
  if (!currentJob?.job_id) {
    return;
  }
  setLoading(true);
  const res = await fetch(`/api/jobs/${currentJob.job_id}/resume`, {method: "POST"});
  const data = await res.json();
  if (!res.ok) {
    setLoading(false);
    setJobMetaText("继续任务失败，请查看错误日志");
    showErrorLog(data.error || "继续任务失败", {
      title: "继续任务失败",
      subtitle: `任务 ID：${currentJob.job_id}`,
    });
    return;
  }
  renderJob(data);
  startJobStream(currentJob.job_id);
}

function openSettings() {
  selectedModelId = findActiveConfig(activeModelType)?.id || "";
  isCreatingModel = false;
  renderModelSettings();
  settingsDialog.showModal();
}

function renderModelSettings() {
  if (!modelConfigs) {
    return;
  }
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.modelType === activeModelType);
  });
  document.querySelectorAll(".chat-fields").forEach((node) => {
    node.style.display = activeModelType === "chat" ? "" : "none";
  });
  document.querySelectorAll(".image-fields").forEach((node) => {
    node.style.display = activeModelType === "image" ? "" : "none";
  });

  const activeId = modelConfigs[`active_${activeModelType}_config_id`];
  const items = currentModelItems();
  modelList.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("article");
    empty.className = "model-item";
    empty.innerHTML = `
      <div class="model-item-head">
        <h3>暂无模型配置</h3>
      </div>
      <p>点击左侧加号卡片后填写 Base URL、模型名和 API Key。</p>
    `;
    modelList.appendChild(empty);
  }
  for (const item of items) {
    const node = document.createElement("article");
    node.className = `model-item${item.id === activeId ? " is-active" : ""}${item.id === selectedModelId ? " is-selected" : ""}`;
    node.tabIndex = 0;
    node.innerHTML = `
      <div class="model-item-head">
        <h3>${escapeHtml(item.name)}</h3>
        ${item.id === activeId ? '<span class="active-badge"><i></i>启用中</span>' : ""}
      </div>
      <p>${escapeHtml(item.model)}<br />${escapeHtml(item.base_url)}</p>
      <div class="model-item-actions">
        <button class="mini-button" type="button" data-action="active">设为启用</button>
        <button class="mini-button danger-button" type="button" data-action="delete">删除</button>
      </div>
    `;
    node.addEventListener("click", () => selectModel(item));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectModel(item);
      }
    });
    node.querySelector('[data-action="active"]').addEventListener("click", (event) => {
      event.stopPropagation();
      activateModel(item.id);
    });
    node.querySelector('[data-action="delete"]').addEventListener("click", (event) => {
      event.stopPropagation();
      deleteModel(item.id);
    });
    modelList.appendChild(node);
  }
  const addButton = document.createElement("button");
  addButton.className = `add-model-card${isCreatingModel ? " is-selected" : ""}`;
  addButton.type = "button";
  addButton.title = activeModelType === "chat" ? "新建对话模型" : "新建生图模型";
  addButton.innerHTML = `<span>+</span>`;
  addButton.addEventListener("click", () => {
    selectedModelId = "";
    isCreatingModel = true;
    resetModelForm(defaultModelConfig());
    renderModelSettings();
  });
  modelList.appendChild(addButton);

  if (isCreatingModel) {
    resetModelForm(defaultModelConfig());
  } else if (!modelConfigId.value) {
    const selected = items.find((item) => item.id === selectedModelId);
    const active = items.find((item) => item.id === activeId);
    fillModelForm(selected || active || defaultModelConfig());
  }
}

function fillModelForm(item) {
  modelConfigId.value = item.id || "";
  if (item.id) {
    selectedModelId = item.id;
  }
  modelName.value = item.name || "";
  modelBaseUrl.value = item.base_url || "https://anyaigc.com/v1";
  modelApiKey.value = item.api_key || "";
  modelNameValue.value = item.model || (activeModelType === "chat" ? "gpt-5.5" : "gpt-image-2");
  modelTemperature.value = item.temperature ?? 0.3;
  modelMaxTokens.value = item.max_tokens ?? 5000;
  modelOutputFormat.value = item.output_format || "png";
  modelFormMessage.textContent = item.id ? `正在编辑：${item.name}` : "正在新建配置";
}

function resetModelForm(item) {
  modelConfigId.value = "";
  modelName.value = item.name || "";
  modelBaseUrl.value = item.base_url || "https://anyaigc.com/v1";
  modelApiKey.value = item.api_key || "";
  modelNameValue.value = item.model || (activeModelType === "chat" ? "gpt-5.5" : "gpt-image-2");
  modelTemperature.value = item.temperature ?? 0.3;
  modelMaxTokens.value = item.max_tokens ?? 5000;
  modelOutputFormat.value = item.output_format || "png";
  modelFormMessage.textContent = "正在新建配置";
}

function selectModel(item) {
  isCreatingModel = false;
  fillModelForm(item);
  renderModelSettings();
}

function defaultModelConfig() {
  if (activeModelType === "chat") {
    return {
      name: "新的对话模型",
      base_url: "https://anyaigc.com/v1",
      api_key: "",
      model: "gpt-5.5",
      temperature: 0.3,
      max_tokens: 5000,
    };
  }
  return {
    name: "新的生图模型",
    base_url: "https://anyaigc.com/v1",
    api_key: "",
    model: "gpt-image-2",
    output_format: "png",
  };
}

function collectModelPayload() {
  const payload = {
    name: modelName.value.trim(),
    base_url: modelBaseUrl.value.trim(),
    api_key: modelApiKey.value.trim(),
    model: modelNameValue.value.trim(),
    enabled: true,
  };
  if (activeModelType === "chat") {
    payload.temperature = Number(modelTemperature.value || 0.3);
    payload.max_tokens = Number(modelMaxTokens.value || 5000);
  } else {
    payload.output_format = modelOutputFormat.value.trim() || "png";
  }
  return payload;
}

async function saveModel(event) {
  event.preventDefault();
  if (!modelName.value.trim() || !modelBaseUrl.value.trim() || !modelNameValue.value.trim()) {
    modelFormMessage.textContent = "配置名称、Base URL 和模型名不能为空";
    return;
  }
  const id = modelConfigId.value;
  const url = id ? `/api/model-configs/${activeModelType}/${id}` : `/api/model-configs/${activeModelType}`;
  const method = id ? "PUT" : "POST";
  const res = await fetch(url, {
    method,
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(collectModelPayload()),
  });
  const data = await res.json();
  if (!res.ok) {
    modelFormMessage.textContent = data.error || "保存失败";
    return;
  }
  modelFormMessage.textContent = `已保存：${data.name || ""}`;
  await loadModelConfigs();
  const savedItem = currentModelItems().find((item) => item.id === data.id);
  if (!savedItem) {
    modelFormMessage.textContent = `保存后未在 ${activeModelType} 列表中找到新配置，请刷新页面重试`;
    return;
  }
  selectedModelId = data.id || "";
  isCreatingModel = false;
  fillModelForm(savedItem);
  renderModelSettings();
  updateModeText();
}

async function activateModel(id) {
  const res = await fetch(`/api/model-configs/${activeModelType}/${id}/active`, {method: "POST"});
  const data = await res.json();
  if (!res.ok) {
    modelFormMessage.textContent = data.error || "启用失败";
    return;
  }
  await loadModelConfigs();
  renderModelSettings();
  updateModeText();
}

async function deleteModel(id) {
  if (!window.confirm("确定删除这个模型配置？")) {
    return;
  }
  const res = await fetch(`/api/model-configs/${activeModelType}/${id}`, {method: "DELETE"});
  const data = await res.json();
  if (!res.ok) {
    modelFormMessage.textContent = data.error || "删除失败";
    return;
  }
  modelConfigId.value = "";
  selectedModelId = "";
  isCreatingModel = false;
  await loadModelConfigs();
  renderModelSettings();
  updateModeText();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!config) {
    return;
  }

  const selectedPages = Number(pageCount.value);
  const selectedPreset = config.image_presets[imagePreset.value];
  if (selectedPages > config.max_pages) {
    setJobMetaText("创建任务失败，请查看错误日志");
    showErrorLog(`页数不能超过 ${config.max_pages}`, {
      title: "创建任务失败",
      subtitle: "参数校验未通过",
    });
    return;
  }

  stopJobStream();
  stageOpenState = {};
  pagesGrid.innerHTML = "";
  stageTimeline.innerHTML = "";
  currentPreviewPageNo = 1;
  setLoading(true);
  const targetLabel = jobTarget.value === "reference_only" ? "图片版 PPT" : "可编辑 PPT";
  setJobMetaText(`准备生成 ${selectedPreset.label} ${targetLabel}，任务创建中...`);

  try {
    const formData = new FormData(form);
    formData.set("include_cover_page", includeCoverPage.checked ? "1" : "0");
    formData.set("page_richness_default", normalizePageRichnessValue(pageRichnessDefault.value, defaultPageRichnessValue()));
    formData.set(
      "page_richness_map",
      JSON.stringify(
        readExplicitPageRichnessMap(pageRichnessDefault.value)
      )
    );
    const res = await fetch("/api/jobs", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "生成失败");
    }
    renderJob(data);
    startJobStream(data.job_id);
  } catch (error) {
    setLoading(false);
    setJobMetaText("创建任务失败，请查看错误日志");
    showErrorLog(error.message, {
      title: "创建任务失败",
      subtitle: "任务尚未成功创建",
    });
  }
});

clearButton.addEventListener("click", () => {
  resetWorkspaceView("等待提交任务");
});

newTaskButton.addEventListener("click", () => startNewTask(true));
settingsButton.addEventListener("click", openSettings);
closeSettingsButton.addEventListener("click", () => settingsDialog.close());
editContentButton.addEventListener("click", openContentDialog);
contentPreviewCard.addEventListener("click", openContentDialog);
saveContentButton.addEventListener("click", saveContentDraft);
cancelContentButton.addEventListener("click", closeContentDialog);
closeContentButton.addEventListener("click", closeContentDialog);
contentEditor.addEventListener("input", () => {
  const summary = summarizeContent(contentEditor.value);
  contentPreviewTitle.textContent = summary.title;
  contentPreviewText.textContent = summary.preview;
});
interruptButton.addEventListener("click", interruptCurrentJob);
resumeButton.addEventListener("click", resumeCurrentJob);
deliveryResult?.addEventListener("click", (event) => {
  const trigger = event.target.closest('[data-action="open-error-log"]');
  if (!trigger || !currentJob) {
    return;
  }
  showJobError(currentJob);
});
modelForm.addEventListener("submit", saveModel);
document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    activeModelType = button.dataset.modelType;
    modelConfigId.value = "";
    selectedModelId = findActiveConfig(activeModelType)?.id || "";
    isCreatingModel = false;
    renderModelSettings();
  });
});
imagePreset.addEventListener("change", updatePresetSummary);
pageCount.addEventListener("change", () => renderPageRichnessControls(Number(pageCount.value || 0)));
pageRichnessDefault.addEventListener("change", () => renderPageRichnessControls(Number(pageCount.value || 0)));
styleImages.addEventListener("change", syncStyleReferenceSelectionHint);
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "j") {
    event.preventDefault();
    startNewTask(true);
  }
});

loadConfig();
syncJobActionButtons();
syncContentPreview();
renderWorkspaceStatus(null);
