(function attachPageRichnessHelpers(globalScope) {
  const PAGE_RICHNESS_LABELS = {
    low: "低",
    medium: "中",
    high: "高",
  };

  function normalizePageRichnessValue(value, fallback = "medium") {
    const normalized = String(value || "").trim().toLowerCase();
    if (Object.prototype.hasOwnProperty.call(PAGE_RICHNESS_LABELS, normalized)) {
      return normalized;
    }
    return String(fallback || "medium").trim().toLowerCase() || "medium";
  }

  function formatPageRichnessLabel(value, fallback = "medium") {
    const normalized = normalizePageRichnessValue(value, fallback);
    return PAGE_RICHNESS_LABELS[normalized] || PAGE_RICHNESS_LABELS.medium;
  }

  function formatPageRichnessText(value, fallback = "medium") {
    return `丰富度 ${formatPageRichnessLabel(value, fallback)}`;
  }

  function listPageRichnessOptions() {
    return Object.entries(PAGE_RICHNESS_LABELS).map(([value, label]) => ({ value, label }));
  }

  globalScope.PptPageRichness = {
    labels: PAGE_RICHNESS_LABELS,
    normalizeValue: normalizePageRichnessValue,
    formatLabel: formatPageRichnessLabel,
    formatText: formatPageRichnessText,
    listOptions: listPageRichnessOptions,
  };
})(window);
