const asText = (value) => String(value || '').trim();
const asBoolean = (value) => value === true || ['1', 'true', 'yes', 'on'].includes(String(value || '').trim().toLowerCase());

const asList = (value) => {
  if (Array.isArray(value)) {
    return value.map((item) => asText(item)).filter(Boolean);
  }
  const text = asText(value);
  return text ? text.split('\n').map((item) => item.trim()).filter(Boolean) : [];
};

export function normalizePagePlan(page = {}, index = 0) {
  return {
    page_no: Number(page.page_no || index + 1),
    title: asText(page.title) || `第 ${index + 1} 页`,
    summary: asText(page.summary),
    bullets: asList(page.bullets),
    layout_intent: asText(page.layout_intent),
    layout_family: asText(page.layout_family),
    page_richness: asText(page.page_richness),
    visual_suggestion: asText(page.visual_suggestion || page.style_constraints),
    reference_mode: asText(page.reference_mode) || 'generation',
    prompt_profile: asText(page.prompt_profile) || 'compressed',
    reference_prompt: asText(page.reference_prompt || page.image_prompt),
    elements_prompt: asText(page.elements_prompt),
    reference_prompt_manual: asBoolean(page.reference_prompt_manual),
    elements_prompt_manual: asBoolean(page.elements_prompt_manual),
    reference_prompt_stale: asBoolean(page.reference_prompt_stale),
    elements_prompt_stale: asBoolean(page.elements_prompt_stale),
    layout_slots: asList(page.layout_slots),
    texts: Array.isArray(page.texts) ? page.texts : [],
    element_plan: page.element_plan && typeof page.element_plan === 'object' ? page.element_plan : {},
  };
}

export function normalizePlan(plan = {}) {
  const pages = Array.isArray(plan.pages)
    ? plan.pages.map((page, index) => normalizePagePlan(page, index))
    : [];
  return {
    title: asText(plan.title),
    summary: asText(plan.summary || plan.narrative),
    audience: asText(plan.audience),
    style_type: asText(plan.style_type),
    style_notes: asText(plan.style_notes),
    style_guide: plan.style_guide && typeof plan.style_guide === 'object' ? plan.style_guide : {},
    generation_options: plan.generation_options && typeof plan.generation_options === 'object' ? plan.generation_options : {},
    image_preset: plan.image_preset && typeof plan.image_preset === 'object' ? plan.image_preset : {},
    page_count: pages.length,
    pages,
  };
}

export function renumberPlanPages(pages) {
  return pages.map((page, index) => ({ ...page, page_no: index + 1 }));
}

export function createBlankPagePlan(pageNo) {
  return normalizePagePlan(
    {
      page_no: pageNo,
      title: `第 ${pageNo} 页`,
      summary: '',
      bullets: [],
      reference_prompt: '',
    },
    pageNo - 1,
  );
}
