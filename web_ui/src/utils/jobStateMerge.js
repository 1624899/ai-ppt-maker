const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

const isObjectRecord = (value) => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
);

const mergeObjectField = (currentValue, incomingValue) => {
  if (isObjectRecord(currentValue) && isObjectRecord(incomingValue)) {
    return { ...currentValue, ...incomingValue };
  }
  if (incomingValue !== undefined) return incomingValue;
  return currentValue;
};

const normalizeKey = (value) => String(value || '').trim();

function mergeStages(currentStages, incomingStages) {
  if (!Array.isArray(incomingStages)) {
    return Array.isArray(currentStages) ? currentStages : incomingStages;
  }

  const currentByKey = new Map();
  const currentByIndex = new Map();
  if (Array.isArray(currentStages)) {
    currentStages.forEach((stage, index) => {
      if (!isObjectRecord(stage)) return;
      const key = normalizeKey(stage.key);
      if (key) currentByKey.set(key, stage);
      currentByIndex.set(index, stage);
    });
  }

  const seenKeys = new Set();
  const mergedStages = incomingStages.map((stage, index) => {
    if (!isObjectRecord(stage)) return stage;
    const key = normalizeKey(stage.key);
    const currentStage = (key && currentByKey.get(key)) || currentByIndex.get(index) || {};
    if (key) seenKeys.add(key);
    const mergedStage = { ...currentStage, ...stage };
    if (isObjectRecord(currentStage.data) || isObjectRecord(stage.data)) {
      mergedStage.data = mergeObjectField(currentStage.data, stage.data);
    }
    return mergedStage;
  });

  if (Array.isArray(currentStages)) {
    currentStages.forEach((stage) => {
      if (!isObjectRecord(stage)) return;
      const key = normalizeKey(stage.key);
      if (key && !seenKeys.has(key)) mergedStages.push(stage);
    });
  }

  return mergedStages;
}

export function mergeJobState(currentJob, incomingJob) {
  if (incomingJob == null) return incomingJob;
  if (!isObjectRecord(incomingJob)) return incomingJob;
  if (!isObjectRecord(currentJob)) return incomingJob;

  const currentJobId = normalizeKey(currentJob.job_id);
  const incomingJobId = normalizeKey(incomingJob.job_id);
  if (currentJobId && incomingJobId && currentJobId !== incomingJobId) {
    return incomingJob;
  }

  const merged = { ...currentJob, ...incomingJob };

  if (hasOwn(incomingJob, 'job_meta') || hasOwn(currentJob, 'job_meta')) {
    merged.job_meta = mergeObjectField(currentJob.job_meta, incomingJob.job_meta);
  }
  if (hasOwn(incomingJob, 'result') || hasOwn(currentJob, 'result')) {
    merged.result = mergeObjectField(currentJob.result, incomingJob.result);
  }
  if (hasOwn(incomingJob, 'stages') || hasOwn(currentJob, 'stages')) {
    merged.stages = mergeStages(currentJob.stages, incomingJob.stages);
  }

  return merged;
}
