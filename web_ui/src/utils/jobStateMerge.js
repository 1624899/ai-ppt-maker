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

const mergeResultField = (currentValue, incomingValue) => {
  if (incomingValue === undefined) return currentValue;
  if (!isObjectRecord(incomingValue)) return incomingValue;
  if (!isObjectRecord(currentValue)) return incomingValue;

  const merged = { ...currentValue, ...incomingValue };
  if (hasOwn(incomingValue, 'deliveries')) {
    merged.deliveries = incomingValue.deliveries;
  }
  if (hasOwn(incomingValue, 'editable_delivery_bundle')) {
    merged.editable_delivery_bundle = incomingValue.editable_delivery_bundle;
  }
  return merged;
};

const isEmptyObject = (value) => isObjectRecord(value) && Object.keys(value).length === 0;

const resultClearsDeliveryState = (result) => (
  isObjectRecord(result)
  && (
    (hasOwn(result, 'deliveries') && isEmptyObject(result.deliveries))
    || (hasOwn(result, 'editable_delivery_bundle') && isEmptyObject(result.editable_delivery_bundle))
  )
);

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
    merged.result = mergeResultField(currentJob.result, incomingJob.result);
  }
  if (hasOwn(incomingJob, 'delivery_actions')) {
    merged.delivery_actions = incomingJob.delivery_actions;
  } else if (resultClearsDeliveryState(incomingJob.result)) {
    merged.delivery_actions = [];
  }
  if (hasOwn(incomingJob, 'stages') || hasOwn(currentJob, 'stages')) {
    merged.stages = mergeStages(currentJob.stages, incomingJob.stages);
  }

  return merged;
}
