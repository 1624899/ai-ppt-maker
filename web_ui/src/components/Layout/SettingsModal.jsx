/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, Eye, EyeOff, Loader2, Plus, Trash2, X } from 'lucide-react';
import clsx from 'clsx';
import { useModelConfigs } from '../../hooks/useModelConfigs';

const DEFAULT_BASE_URL = 'https://your-api-endpoint.com/v1';

const MODEL_TYPES = [
  { value: 'chat', label: '对话模型', description: '内容规划、脚本生成与评估使用' },
  { value: 'image', label: '生图模型', description: 'PPT 页面原稿图生成使用' },
];

const createModelDefaults = (modelType) => {
  if (modelType === 'chat') {
    return {
      name: '新的对话模型',
      base_url: DEFAULT_BASE_URL,
      api_key: '',
      model: '',
      temperature: 0.3,
      max_tokens: 5000,
    };
  }
  return {
    name: '新的生图模型',
    base_url: DEFAULT_BASE_URL,
    api_key: '',
    model: '',
    output_format: 'png',
  };
};

const createFormValues = (modelType, item = null) => {
  const defaults = createModelDefaults(modelType);
  return {
    id: item?.id || '',
    name: item?.name || defaults.name,
    base_url: item?.base_url || defaults.base_url,
    api_key: item?.api_key || '',
    model: item?.model || defaults.model,
    temperature: item?.temperature ?? defaults.temperature ?? 0.3,
    max_tokens: item?.max_tokens ?? defaults.max_tokens ?? 5000,
    output_format: item?.output_format || defaults.output_format || 'png',
    api_key_configured: Boolean(item?.api_key_configured),
  };
};

const SettingsModal = ({ isOpen, onClose }) => {
  const {
    modelConfigs,
    loading,
    error,
    reload,
    saveModelConfig,
    activateModelConfig,
    deleteModelConfig,
  } = useModelConfigs(isOpen);
  const [activeModelType, setActiveModelType] = useState('chat');
  const [selectedModelId, setSelectedModelId] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState(() => createFormValues('chat'));
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);

  const activeId = modelConfigs?.[`active_${activeModelType}_config_id`] || '';
  const items = useMemo(() => modelConfigs?.configs?.[activeModelType] || [], [activeModelType, modelConfigs]);
  const selectedItem = useMemo(() => {
    return items.find((item) => item.id === selectedModelId) || items.find((item) => item.id === activeId) || null;
  }, [activeId, items, selectedModelId]);

  useEffect(() => {
    if (!isOpen || !modelConfigs) return;
    const nextItem = selectedItem;
    setIsCreating(false);
    setSelectedModelId(nextItem?.id || '');
    setForm(createFormValues(activeModelType, nextItem));
    setMessage(nextItem ? `正在编辑：${nextItem.name}` : '暂无配置，请新建模型');
    setShowApiKey(false);
  }, [activeModelType, isOpen, modelConfigs, selectedItem]);

  const updateForm = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const selectModel = (item) => {
    setIsCreating(false);
    setSelectedModelId(item.id);
    setForm(createFormValues(activeModelType, item));
    setMessage(`正在编辑：${item.name}`);
    setShowApiKey(false);
  };

  const startCreate = () => {
    setIsCreating(true);
    setSelectedModelId('');
    setForm(createFormValues(activeModelType));
    setMessage('正在新建配置');
    setShowApiKey(false);
  };

  const collectPayload = () => {
    const payload = {
      name: form.name.trim(),
      base_url: form.base_url.trim(),
      api_key: form.api_key.trim(),
      model: form.model.trim(),
      enabled: true,
    };
    if (activeModelType === 'chat') {
      payload.temperature = Number(form.temperature || 0.3);
      payload.max_tokens = Number(form.max_tokens || 5000);
    } else {
      payload.output_format = form.output_format.trim() || 'png';
    }
    return payload;
  };

  const handleSave = async (event) => {
    event.preventDefault();
    if (!form.name.trim() || !form.base_url.trim() || !form.model.trim()) {
      setMessage('配置名称、Base URL 和模型名不能为空');
      return;
    }
    if (!form.id && !form.api_key.trim()) {
      setMessage('新建配置时必须填写 API Key');
      return;
    }

    setSaving(true);
    try {
      const saved = await saveModelConfig({ modelType: activeModelType, id: form.id, payload: collectPayload() });
      await reload();
      setIsCreating(false);
      setSelectedModelId(saved.id || '');
      setForm(createFormValues(activeModelType, saved));
      setMessage(`已保存：${saved.name || ''}`);
      setShowApiKey(false);
    } catch (err) {
      setMessage(err.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleActivate = async (id) => {
    try {
      await activateModelConfig({ modelType: activeModelType, id });
      await reload();
      setMessage('已切换启用模型');
    } catch (err) {
      setMessage(err.message || '启用失败');
    }
  };

  const handleDelete = async (id) => {
    const confirmed = window.confirm('确定删除这个模型配置？');
    if (!confirmed) return;
    try {
      await deleteModelConfig({ modelType: activeModelType, id });
      setSelectedModelId('');
      setIsCreating(false);
      await reload();
      setMessage('已删除模型配置');
    } catch (err) {
      setMessage(err.message || '删除失败');
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="settings-modal"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <button type="button" className="settings-modal__backdrop" aria-label="关闭设置" onClick={onClose} />
          <motion.section
            className="settings-modal__shell"
            initial={{ scale: 0.96, y: 18 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.96, y: 18 }}
            role="dialog"
            aria-modal="true"
            aria-label="模型配置"
          >
            <header className="settings-modal__head">
              <div>
                <h2>模型配置</h2>
                <p>管理 OpenAI-compatible 对话模型与生图模型。</p>
              </div>
              <button type="button" className="icon-button" onClick={onClose} title="关闭" aria-label="关闭">
                <X size={18} />
              </button>
            </header>

            <div className="settings-tabs" role="tablist" aria-label="模型类型">
              {MODEL_TYPES.map((type) => (
                <button
                  type="button"
                  key={type.value}
                  className={clsx('tab-button', activeModelType === type.value && 'is-active')}
                  onClick={() => {
                    setActiveModelType(type.value);
                    setSelectedModelId('');
                    setIsCreating(false);
                  }}
                >
                  <strong>{type.label}</strong>
                  <span>{type.description}</span>
                </button>
              ))}
            </div>

            {loading && !modelConfigs ? (
              <div className="settings-loading">
                <Loader2 className="spin" size={24} />
                <span>正在加载模型配置...</span>
              </div>
            ) : error ? (
              <div className="settings-empty is-error">{error}</div>
            ) : (
              <div className="settings-body">
                <aside className="model-list" aria-label="模型配置列表">
                  {items.length === 0 && (
                    <article className="model-item">
                      <h3>暂无模型配置</h3>
                      <p>新建后填写 Base URL、模型名和 API Key。</p>
                    </article>
                  )}
                  {items.map((item) => (
                    <article
                      key={item.id}
                      className={clsx('model-item', item.id === activeId && 'is-active', item.id === form.id && !isCreating && 'is-selected')}
                    >
                      <button type="button" className="model-item__main" onClick={() => selectModel(item)}>
                        <span className="model-item__head">
                          <strong>{item.name}</strong>
                          {item.id === activeId && (
                            <em>
                              <CheckCircle2 size={13} />
                              启用中
                            </em>
                          )}
                        </span>
                        <span>{item.model}</span>
                        <small>{item.base_url}</small>
                      </button>
                      <div className="model-item__actions">
                        <button type="button" onClick={() => handleActivate(item.id)} disabled={item.id === activeId}>
                          设为启用
                        </button>
                        <button type="button" className="is-danger" onClick={() => handleDelete(item.id)} title="删除">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </article>
                  ))}
                  <button type="button" className={clsx('add-model-card', isCreating && 'is-selected')} onClick={startCreate}>
                    <Plus size={20} />
                    <span>{activeModelType === 'chat' ? '新建对话模型' : '新建生图模型'}</span>
                  </button>
                </aside>

                <form className="model-form" onSubmit={handleSave}>
                  <input type="hidden" value={form.id} readOnly />
                  <label className="field">
                    <span>配置名称</span>
                    <input value={form.name} onChange={(event) => updateForm('name', event.target.value)} />
                  </label>
                  <label className="field">
                    <span>Base URL</span>
                    <input
                      value={form.base_url}
                      onChange={(event) => updateForm('base_url', event.target.value)}
                      placeholder={DEFAULT_BASE_URL}
                    />
                    <small>填写兼容 OpenAI Response 格式的服务端点地址。</small>
                  </label>
                  <div className="model-form__grid">
                    <label className="field">
                      <span>API Key</span>
                      <span className="secret-input-shell">
                        <input
                          type={showApiKey ? 'text' : 'password'}
                          autoComplete="off"
                          value={form.api_key}
                          onChange={(event) => updateForm('api_key', event.target.value)}
                        />
                        {(form.api_key_configured || form.api_key) && (
                          <button
                            type="button"
                            className="secret-preview-toggle"
                            onClick={() => setShowApiKey((value) => !value)}
                            title={showApiKey ? '隐藏完整密钥' : '显示完整密钥'}
                            aria-label={showApiKey ? '隐藏完整密钥' : '显示完整密钥'}
                          >
                            {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                          </button>
                        )}
                      </span>
                    </label>
                    <label className="field">
                      <span>模型名</span>
                      <input value={form.model} onChange={(event) => updateForm('model', event.target.value)} placeholder="直接填写模型名" />
                    </label>
                  </div>

                  {activeModelType === 'chat' ? (
                    <div className="model-form__grid">
                      <label className="field">
                        <span>Temperature</span>
                        <input
                          type="number"
                          min="0"
                          max="2"
                          step="0.1"
                          value={form.temperature}
                          onChange={(event) => updateForm('temperature', event.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Max tokens</span>
                        <input
                          type="number"
                          min="512"
                          step="256"
                          value={form.max_tokens}
                          onChange={(event) => updateForm('max_tokens', event.target.value)}
                        />
                      </label>
                    </div>
                  ) : (
                    <label className="field">
                      <span>输出格式</span>
                      <input value={form.output_format} onChange={(event) => updateForm('output_format', event.target.value)} placeholder="png" />
                    </label>
                  )}

                  <div className="model-form__actions">
                    <p className="model-form__message">{message}</p>
                    <button type="submit" className="btn btn-primary" disabled={saving}>
                      {saving && <Loader2 className="spin" size={16} />}
                      <span>{saving ? '保存中...' : '保存配置'}</span>
                    </button>
                  </div>
                </form>
              </div>
            )}
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default SettingsModal;
