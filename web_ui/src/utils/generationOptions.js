const TRUE_VALUES = new Set(['1', 'true', 'yes', 'on']);
const FALSE_VALUES = new Set(['0', 'false', 'no', 'off', '']);

export const parseBooleanOption = (value, fallback = false) => {
  if (typeof value === 'boolean') return value;
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'number') return value !== 0;

  const normalized = String(value).trim().toLowerCase();
  if (TRUE_VALUES.has(normalized)) return true;
  if (FALSE_VALUES.has(normalized)) return false;
  return fallback;
};

export const getDefaultIncludeCoverPage = (config) => (
  parseBooleanOption(config?.default_include_cover_page, true)
);

export const getJobGenerationOptions = (job) => {
  const generationOptions = job?.job_meta?.generation_options;
  return generationOptions && typeof generationOptions === 'object' ? generationOptions : {};
};

export const resolveIncludeCoverPage = (config, job) => {
  const defaultValue = getDefaultIncludeCoverPage(config);
  const generationOptions = getJobGenerationOptions(job);

  if (Object.prototype.hasOwnProperty.call(generationOptions, 'include_cover_page')) {
    return parseBooleanOption(generationOptions.include_cover_page, defaultValue);
  }

  const meta = job?.job_meta || {};
  if (Object.prototype.hasOwnProperty.call(meta, 'include_cover_page')) {
    return parseBooleanOption(meta.include_cover_page, defaultValue);
  }

  return defaultValue;
};
