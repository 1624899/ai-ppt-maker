import { useEffect, useEffectEvent, useState } from 'react';
import { FileImage, FileText, WandSparkles } from 'lucide-react';
import { useConfig } from '../../hooks/useConfig';
import { resolveIncludeCoverPage } from '../../utils/generationOptions';
import { getJobMeta } from '../../utils/jobPresentation';
import { getWorkflowSubmitLabel, getWorkflowModeFromJob, normalizeWorkflowMode, WORKFLOW_MODE_AUTO } from '../../utils/workflowMode';
import ImageUploadPreviewList from './ImageUploadPreviewList';
import WorkflowModeSwitch from './WorkflowModeSwitch';

const RICHNESS_LEVELS = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
];

const REFERENCE_STYLE_ADHERENCE_FALLBACKS = [
  { value: 'loose', label: '宽松' },
  { value: 'balanced', label: '适度' },
  { value: 'strict', label: '严格' },
];

const SOURCE_MODES = {
  PROMPT: 'prompt',
  EXTERNAL_REFERENCE: 'external_reference',
};

const RESIZE_MODE_OPTIONS = [
  { value: 'stretch', label: '拉伸填满' },
  { value: 'contain', label: '等比留白' },
  { value: 'cover', label: '等比裁切' },
];

const buildPageRichnessMap = (list) => {
  return list.reduce((acc, value, index) => {
    if (value) acc[String(index + 1)] = value;
    return acc;
  }, {});
};

const resizeRichnessList = (list, pageCount) => {
  const next = list.slice(0, pageCount);
  while (next.length < pageCount) next.push('');
  return next;
};

const clampPageCount = (value, maxPages) => {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return 1;
  return Math.min(Math.max(parsed, 1), maxPages);
};

const createInitialValues = (config, currentJob, workflowMode) => {
  const meta = getJobMeta(currentJob);
  const generationOptions = meta.generation_options || {};
  const richnessMap = generationOptions.page_richness_map || {};
  const pageCount = Number(meta.page_count || currentJob?.page_count || config.default_pages || 4);

  return {
    sourceMode: SOURCE_MODES.PROMPT,
    content: String(meta.content || currentJob?.content || ''),
    pageCount,
    imagePreset: String(meta.image_preset?.name || currentJob?.image_preset || config.default_image_preset || ''),
    styleNotes: String(meta.style_notes || currentJob?.style_notes || ''),
    jobTarget: String(meta.job_target || 'editable_ppt'),
    workflowMode: normalizeWorkflowMode(workflowMode || getWorkflowModeFromJob(currentJob) || WORKFLOW_MODE_AUTO),
    imageQuality: String(meta.image_quality || currentJob?.image_quality || 'medium'),
    includeCoverPage: resolveIncludeCoverPage(config, currentJob),
    pageRichnessDefault: String(generationOptions.page_richness_default || 'medium'),
    referenceStyleAdherence: String(
      generationOptions.reference_style_adherence || config.default_reference_style_adherence || 'balanced',
    ),
    pageRichnessList: Array.from({ length: pageCount }, (_, index) => String(richnessMap[String(index + 1)] || '')),
    externalReferenceResizeMode: 'stretch',
    externalReferenceCreateOnly: false,
  };
};

const CreationFormFields = ({
  config,
  currentJob,
  compact,
  workflowMode,
  submitLabel,
  onWorkflowModeChange,
  onCreated,
  onParamsChange,
}) => {
  const [form, setForm] = useState(() => createInitialValues(config, currentJob, workflowMode));
  const [styleFiles, setStyleFiles] = useState([]);
  const [referenceFiles, setReferenceFiles] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const emitParamsChange = useEffectEvent((nextForm) => {
    onParamsChange?.(nextForm);
  });

  const updateForm = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (field === 'workflowMode') {
      onWorkflowModeChange?.(value);
    }
  };

  useEffect(() => {
    emitParamsChange(form);
  }, [form]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setError('');
    setSubmitting(true);

    const formData = new FormData();
    formData.append('source_mode', form.sourceMode);
    formData.append('content', form.content);
    formData.append('image_preset', form.imagePreset);
    formData.append('image_quality', form.imageQuality);
    if (form.sourceMode === SOURCE_MODES.EXTERNAL_REFERENCE) {
      if (referenceFiles.length === 0) {
        setError('请先上传至少一张原稿图。');
        setSubmitting(false);
        return;
      }
      formData.append('job_target', form.externalReferenceCreateOnly ? 'reference_only' : 'editable_ppt');
      formData.append('external_reference_resize_mode', form.externalReferenceResizeMode);
      formData.append('external_reference_create_only', String(form.externalReferenceCreateOnly));
      referenceFiles.forEach((file) => formData.append('reference_images', file));
    } else {
      formData.append('page_count', String(form.pageCount));
      formData.append('style_notes', form.styleNotes);
      formData.append('job_target', form.jobTarget);
      formData.append('workflow_mode', form.workflowMode);
      formData.append('include_cover_page', String(form.includeCoverPage));
      formData.append('page_richness_default', form.pageRichnessDefault);
      formData.append('reference_style_adherence', form.referenceStyleAdherence);
      formData.append('page_richness_map', JSON.stringify(buildPageRichnessMap(form.pageRichnessList)));
      if (currentJob?.job_id && styleFiles.length === 0) {
        formData.append('reuse_style_refs_from_job_id', currentJob.job_id);
      }
      styleFiles.forEach((file) => formData.append('style_images', file));
    }

    try {
      const response = await fetch('/api/jobs', {
        method: 'POST',
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || '提交失败');
      }
      onCreated?.(payload);
    } catch (err) {
      setError(err.message || '请求异常');
    } finally {
      setSubmitting(false);
    }
  };

  const presets = config?.image_presets || {};
  const maxPages = Number(config?.max_pages || 20);
  const isExternalReferenceMode = form.sourceMode === SOURCE_MODES.EXTERNAL_REFERENCE;
  const submitText = (() => {
    if (submitting) return '正在提交...';
    if (isExternalReferenceMode) {
      return form.externalReferenceCreateOnly ? '登记原稿图任务' : '导入并继续转换';
    }
    if (submitLabel) return submitLabel;
    return currentJob ? `基于当前任务${getWorkflowSubmitLabel(form.workflowMode)}` : getWorkflowSubmitLabel(form.workflowMode);
  })();
  const referenceStyleAdherenceOptions = Array.isArray(config?.reference_style_adherence_options)
    ? config.reference_style_adherence_options
    : REFERENCE_STYLE_ADHERENCE_FALLBACKS;

  return (
    <form className="creation-form" onSubmit={handleSubmit}>
      <div className="form-grid">
        <div className="field field--full">
          <span>任务来源</span>
          <div className="source-mode-switch" role="tablist" aria-label="任务来源">
            <button
              type="button"
              className={form.sourceMode === SOURCE_MODES.PROMPT ? 'is-active' : ''}
              onClick={() => updateForm('sourceMode', SOURCE_MODES.PROMPT)}
              disabled={submitting}
            >
              <FileText size={18} />
              <span>
                <strong>从文本生成</strong>
                <small>按 Brief 规划并生成原稿图</small>
              </span>
            </button>
            <button
              type="button"
              className={form.sourceMode === SOURCE_MODES.EXTERNAL_REFERENCE ? 'is-active' : ''}
              onClick={() => updateForm('sourceMode', SOURCE_MODES.EXTERNAL_REFERENCE)}
              disabled={submitting}
            >
              <FileImage size={18} />
              <span>
                <strong>从已有原稿图继续</strong>
                <small>跳过原稿图生成，直接进入元素图转换</small>
              </span>
            </button>
          </div>
        </div>

        {!isExternalReferenceMode && (
          <div className="field field--full">
            <span>生成工作流</span>
            <WorkflowModeSwitch
              value={form.workflowMode}
              onChange={(value) => updateForm('workflowMode', value)}
              disabled={submitting}
            />
          </div>
        )}

        <label className={compact ? 'field field--wide' : 'field field--full'}>
          <span>任务内容</span>
          <textarea
            value={form.content}
            onChange={(event) => updateForm('content', event.target.value)}
            placeholder={isExternalReferenceMode ? '可选，用于任务命名和记录，例如：外部设计稿转可编辑 PPT...' : '粘贴汇报大纲、会议纪要或你想表达的 PPT 内容...'}
            required={!isExternalReferenceMode}
            rows={isExternalReferenceMode ? 3 : compact ? 5 : 7}
          />
        </label>

        {isExternalReferenceMode ? (
          <div className="field field--full">
            <span>原稿图</span>
            <ImageUploadPreviewList
              files={referenceFiles}
              onChange={setReferenceFiles}
              accept="image/png,image/jpeg,image/webp"
              disabled={submitting}
              emptyTitle="上传已有原稿图"
              emptyHint="支持 PNG、JPG、WEBP，多张图片会按选择顺序生成多页任务。"
              addLabel="继续添加"
              itemLabel="原稿图"
            />
          </div>
        ) : (
          <label className="field">
            <span>页数</span>
            <input
              type="number"
              min="1"
              max={maxPages}
              value={form.pageCount}
              onChange={(event) => {
                const pageCount = clampPageCount(event.target.value || 1, maxPages);
                setForm((prev) => ({
                  ...prev,
                  pageCount,
                  pageRichnessList: resizeRichnessList(prev.pageRichnessList, pageCount),
                }));
              }}
            />
          </label>
        )}

        <label className="field">
          <span>画幅</span>
          <select value={form.imagePreset} onChange={(event) => updateForm('imagePreset', event.target.value)} required>
            {Object.entries(presets).map(([key, preset]) => (
              <option key={key} value={key}>{preset.label}</option>
            ))}
          </select>
        </label>

        {!isExternalReferenceMode && (
          <label className="field">
            <span>输出模式</span>
            <select value={form.jobTarget} onChange={(event) => updateForm('jobTarget', event.target.value)}>
              <option value="editable_ppt">可编辑元素</option>
              <option value="reference_only">图片版 PPT</option>
            </select>
          </label>
        )}

        <label className="field">
          <span>图像质量</span>
          <select value={form.imageQuality} onChange={(event) => updateForm('imageQuality', event.target.value)}>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="low">Low</option>
            <option value="auto">Auto</option>
          </select>
        </label>

        {isExternalReferenceMode ? (
          <>
            <label className="field">
              <span>图片适配</span>
              <select
                value={form.externalReferenceResizeMode}
                onChange={(event) => updateForm('externalReferenceResizeMode', event.target.value)}
              >
                {RESIZE_MODE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>

            <label className="checkbox-row checkbox-row--framed field--full">
              <input
                type="checkbox"
                checked={form.externalReferenceCreateOnly}
                onChange={(event) => updateForm('externalReferenceCreateOnly', event.target.checked)}
              />
              <span>只登记为原稿图任务，稍后再继续生成可编辑元素。</span>
            </label>
          </>
        ) : (
          <>
            <label className="checkbox-row checkbox-row--framed field--full">
              <input
                type="checkbox"
                checked={form.includeCoverPage}
                onChange={(event) => updateForm('includeCoverPage', event.target.checked)}
              />
              <span>包含首页生成，第 1 页作为封面视觉基调。</span>
            </label>

            <label className="field field--full">
              <span>风格补充</span>
              <input
                type="text"
                value={form.styleNotes}
                onChange={(event) => updateForm('styleNotes', event.target.value)}
                placeholder="例如：蓝白科技风、少文字、多流程图、商务汇报感..."
              />
            </label>

            <div className="field field--full">
              <span>内容丰富度</span>
              <div className="richness-control">
                <select value={form.pageRichnessDefault} onChange={(event) => updateForm('pageRichnessDefault', event.target.value)}>
                  {RICHNESS_LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>默认：{level.label}</option>
                  ))}
                </select>
                <div className="richness-pages">
                  {form.pageRichnessList.map((value, index) => (
                    <select
                      key={index}
                      value={value}
                      aria-label={`第 ${index + 1} 页丰富度`}
                      onChange={(event) => {
                        setForm((prev) => {
                          const next = [...prev.pageRichnessList];
                          next[index] = event.target.value;
                          return { ...prev, pageRichnessList: next };
                        });
                      }}
                    >
                      <option value="">第 {index + 1} 页默认</option>
                      {RICHNESS_LEVELS.map((level) => (
                        <option key={level.value} value={level.value}>第 {index + 1} 页：{level.label}</option>
                      ))}
                    </select>
                  ))}
                </div>
              </div>
            </div>

            <label className="field field--full">
              <span>参考风格图约束强度</span>
              <select
                value={form.referenceStyleAdherence}
                onChange={(event) => updateForm('referenceStyleAdherence', event.target.value)}
              >
                {referenceStyleAdherenceOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>

            <div className="field field--full">
              <span>参考风格图</span>
              <ImageUploadPreviewList
                files={styleFiles}
                onChange={setStyleFiles}
                disabled={submitting}
                emptyTitle="上传参考风格图，可选"
                emptyHint={currentJob?.job_id ? '未上传新图时，会复用当前任务参考风格图。' : '支持多张图片一起约束风格。'}
                addLabel="继续添加"
                itemLabel="参考风格图"
              />
            </div>
          </>
        )}

      </div>

      {error && <div className="form-error">{error}</div>}

      <button type="submit" className="btn btn-primary creation-form__submit" disabled={submitting}>
        <WandSparkles size={18} />
        <span>{submitText}</span>
      </button>
    </form>
  );
};

const CreationForm = ({
  currentJob,
  compact = false,
  workflowMode,
  submitLabel,
  onWorkflowModeChange,
  onCreated,
  onParamsChange,
}) => {
  const { config, loading } = useConfig();

  if (loading || !config) {
    return <div className="empty-state">正在加载配置...</div>;
  }

  const formKey = `${currentJob?.job_id || 'new'}-${config.default_image_preset || 'default'}`;
  return (
    <CreationFormFields
      key={formKey}
      config={config}
      currentJob={currentJob}
      compact={compact}
      workflowMode={workflowMode}
      submitLabel={submitLabel}
      onWorkflowModeChange={onWorkflowModeChange}
      onCreated={onCreated}
      onParamsChange={onParamsChange}
    />
  );
};

export default CreationForm;
