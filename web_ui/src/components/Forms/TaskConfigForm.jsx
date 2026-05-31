/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, FileText, Settings, Image as ImageIcon } from 'lucide-react';
import { useConfig } from '../../hooks/useConfig';
import { getDefaultIncludeCoverPage, resolveIncludeCoverPage } from '../../utils/generationOptions';

const REFERENCE_STYLE_ADHERENCE_FALLBACKS = [
  { value: 'loose', label: '宽松' },
  { value: 'balanced', label: '适度' },
  { value: 'strict', label: '严格' },
];

const buildPageRichnessMap = (list) => {
  return list.reduce((acc, value, index) => {
    if (value) acc[String(index + 1)] = value;
    return acc;
  }, {});
};

const CardHeader = ({ title, description, icon: Icon, isOpen, onToggle }) => (
  <div 
    onClick={onToggle}
    style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'space-between',
      cursor: 'pointer',
      padding: '16px 20px',
      background: 'var(--bg-elevated)',
      borderRadius: isOpen ? '16px 16px 0 0' : '16px',
      borderBottom: isOpen ? '1px solid var(--border-light)' : 'none',
      transition: 'background 0.2s'
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <div style={{ padding: '8px', background: 'var(--primary-soft)', borderRadius: '10px', color: 'var(--primary)' }}>
        <Icon size={20} />
      </div>
      <div>
        <h3 style={{ fontSize: '15px', fontWeight: '600', marginBottom: '2px' }}>{title}</h3>
        <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0 }}>{description}</p>
      </div>
    </div>
    <motion.div animate={{ rotate: isOpen ? 180 : 0 }}>
      <ChevronDown size={20} color="var(--text-muted)" />
    </motion.div>
  </div>
);

const TaskConfigForm = ({ currentJob }) => {
  const { config, loading } = useConfig();
  const [openSections, setOpenSections] = useState(['content', 'output', 'style']);
  const [content, setContent] = useState('');
  const [pageCount, setPageCount] = useState(4);
  const [imagePreset, setImagePreset] = useState('');
  const [styleNotes, setStyleNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [stylePreviewUrls, setStylePreviewUrls] = useState([]);
  
  // Newly restored fields
  const [jobTarget, setJobTarget] = useState('editable_ppt');
  const [imageQuality, setImageQuality] = useState('medium');
  const [includeCoverPage, setIncludeCoverPage] = useState(true);
  const [pageRichnessDefault, setPageRichnessDefault] = useState('medium');
  const [referenceStyleAdherence, setReferenceStyleAdherence] = useState('balanced');
  const [pageRichnessList, setPageRichnessList] = useState([]);

  useEffect(() => {
    if (config) {
      setPageCount(config.default_pages || 4);
      setImagePreset(config.default_image_preset || '');
      setReferenceStyleAdherence(config.default_reference_style_adherence || 'balanced');
      if (!currentJob) {
        setIncludeCoverPage(getDefaultIncludeCoverPage(config));
      }
    }
  }, [config, currentJob]);

  useEffect(() => {
    if (currentJob) {
      const meta = currentJob.job_meta || {};
      setContent(currentJob.content || meta.content || '');
      setPageCount(currentJob.page_count || meta.page_count || config?.default_pages || 4);
      setImagePreset(currentJob.image_preset || meta.image_preset?.name || config?.default_image_preset || '');
      setStyleNotes(currentJob.style_notes || meta.style_notes || '');
      
      setJobTarget(meta.job_target || 'editable_ppt');
      setImageQuality(meta.image_quality || 'medium');
      setIncludeCoverPage(resolveIncludeCoverPage(config, currentJob));
      setPageRichnessDefault(meta.generation_options?.page_richness_default || 'medium');
      setReferenceStyleAdherence(
        meta.generation_options?.reference_style_adherence || config?.default_reference_style_adherence || 'balanced',
      );
      const richnessMap = meta.generation_options?.page_richness_map || {};
      const nextPageCount = currentJob.page_count || meta.page_count || config?.default_pages || 4;
      setPageRichnessList(Array.from({ length: nextPageCount }, (_, index) => richnessMap[String(index + 1)] || ''));
    }
  }, [currentJob, config]);

  // Sync pageRichnessList length with pageCount
  useEffect(() => {
    setPageRichnessList(prev => {
      const newList = [...prev];
      if (newList.length < pageCount) {
        for (let i = newList.length; i < pageCount; i++) {
          newList.push(''); // Empty string means use default
        }
      } else if (newList.length > pageCount) {
        newList.splice(pageCount);
      }
      return newList;
    });
  }, [pageCount]);

  const toggleSection = (id) => {
    setOpenSections(prev => 
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    
    setSubmitting(true);
    const formData = new FormData();
    formData.append('content', content);
    formData.append('page_count', pageCount);
    formData.append('image_preset', imagePreset);
    formData.append('style_notes', styleNotes);
    formData.append('job_target', jobTarget);
    formData.append('image_quality', imageQuality);
    formData.append('include_cover_page', includeCoverPage.toString());
    formData.append('page_richness_default', pageRichnessDefault);
    formData.append('reference_style_adherence', referenceStyleAdherence);
    formData.append('page_richness_map', JSON.stringify(buildPageRichnessMap(pageRichnessList)));

    try {
      const res = await fetch('/api/jobs', {
        method: 'POST',
        body: formData
      });
      if (!res.ok) {
        const errData = await res.json();
        alert(errData.error || '提交失败');
      } else {
        // Successful submission
      }
    } catch (err) {
      console.error(err);
      alert('请求异常');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', fontSize: '14px' }}>加载配置中...</div>;
  }

  const presets = config?.image_presets || {};
  const referenceStyleAdherenceOptions = Array.isArray(config?.reference_style_adherence_options)
    ? config.reference_style_adherence_options
    : REFERENCE_STYLE_ADHERENCE_FALLBACKS;

  return (
    <form onSubmit={handleSubmit} className="task-config-form" style={{ display: 'grid', gap: '16px' }}>
      <div style={{ border: '1px solid var(--border-light)', borderRadius: '16px', background: 'var(--bg-card)' }}>
        <CardHeader 
          title="内容输入" 
          description="正文放在独立编辑器里，当前面板只保留摘要预览和入口。"
          icon={FileText}
          isOpen={openSections.includes('content')}
          onToggle={() => toggleSection('content')}
        />
        <AnimatePresence>
          {openSections.includes('content') && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              style={{ overflow: 'hidden' }}
            >
              <div style={{ padding: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <span style={{ fontSize: '14px', fontWeight: '500' }}>汇报内容</span>
                  <button type="button" className="btn btn-secondary" style={{ padding: '4px 12px', fontSize: '12px' }} onClick={() => setEditorOpen(true)}>
                    打开全屏编辑
                  </button>
                </div>
                <div 
                  onClick={() => setEditorOpen(true)}
                  style={{
                  width: '100%',
                  padding: '16px',
                  borderRadius: '12px',
                  background: 'var(--bg-app)',
                  border: '1px solid var(--border-light)',
                  textAlign: 'left',
                  cursor: 'pointer',
                  minHeight: '80px'
                }}>
                  <strong style={{ display: 'block', marginBottom: '4px', fontSize: '14px' }}>
                    {content ? `${content.substring(0, 24)}${content.length > 24 ? '...' : ''}` : '未填写内容'}
                  </strong>
                  <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                    {content ? `${content.substring(0, 120)}${content.length > 120 ? '...' : ''}` : '点击打开全屏编辑器，粘贴完整汇报内容。'}
                  </p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {editorOpen && (
          <motion.div 
            initial={{ opacity: 0 }} 
            animate={{ opacity: 1 }} 
            exit={{ opacity: 0 }}
            style={{ position: 'fixed', inset: 0, zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px' }}
          >
            <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)' }} onClick={() => setEditorOpen(false)} />
            <motion.div 
              initial={{ scale: 0.95, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.95, y: 20 }}
              style={{
                width: '100%', maxWidth: '900px', height: '80vh', background: 'var(--bg-card)', 
                borderRadius: '24px', position: 'relative', display: 'flex', flexDirection: 'column',
                boxShadow: 'var(--shadow-lg)', overflow: 'hidden', border: '1px solid var(--border-light)'
              }}
            >
              <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0, fontSize: '18px' }}>编辑汇报内容</h3>
                <button type="button" className="btn-icon" onClick={() => setEditorOpen(false)}>×</button>
              </div>
              <textarea 
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="在此输入或粘贴汇报大纲..."
                style={{
                  flex: 1, width: '100%', padding: '24px', background: 'var(--bg-app)', border: 'none',
                  resize: 'none', fontSize: '15px', outline: 'none'
                }}
              />
              <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setEditorOpen(false)}>取消</button>
                <button type="button" className="btn btn-primary" onClick={() => setEditorOpen(false)}>确认保存</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <div style={{ border: '1px solid var(--border-light)', borderRadius: '16px', background: 'var(--bg-card)' }}>
        <CardHeader 
          title="输出规格" 
          description="先确定页数、画幅和质量。"
          icon={Settings}
          isOpen={openSections.includes('output')}
          onToggle={() => toggleSection('output')}
        />
        <AnimatePresence>
          {openSections.includes('output') && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              style={{ overflow: 'hidden' }}
            >
              <div style={{ padding: '20px', display: 'grid', gap: '16px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px' }}>指定页数</label>
                    <input type="number" min="1" max={config?.max_pages || 20} value={pageCount} onChange={(e) => setPageCount(parseInt(e.target.value) || 1)} required style={{
                      width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', background: 'var(--bg-app)'
                    }} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px' }}>图像尺寸</label>
                    <select value={imagePreset} onChange={(e) => setImagePreset(e.target.value)} required style={{
                      width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', background: 'var(--bg-app)'
                    }}>
                      {Object.entries(presets).map(([key, preset]) => (
                        <option key={key} value={key}>{preset.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px' }}>输出模式</label>
                    <select value={jobTarget} onChange={(e) => setJobTarget(e.target.value)} required style={{
                      width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', background: 'var(--bg-app)'
                    }}>
                      <option value="reference_only">图片版 PPT</option>
                      <option value="editable_ppt">可编辑元素</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px' }}>图像质量</label>
                    <select value={imageQuality} onChange={(e) => setImageQuality(e.target.value)} required style={{
                      width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', background: 'var(--bg-app)'
                    }}>
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="auto">Auto</option>
                    </select>
                  </div>
                </div>

                <div style={{ display: 'grid', gap: '12px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', cursor: 'pointer' }}>
                    <input type="checkbox" checked={includeCoverPage} onChange={(e) => setIncludeCoverPage(e.target.checked)} />
                    生成 PPT 首页图 (勾选时第1页作为封面)
                  </label>
                </div>

                <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '16px' }}>
                  <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px' }}>默认内容丰富度</label>
                  <select value={pageRichnessDefault} onChange={(e) => setPageRichnessDefault(e.target.value)} required style={{
                    width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', background: 'var(--bg-app)'
                  }}>
                    <option value="low">低 (Low)</option>
                    <option value="medium">中 (Medium)</option>
                    <option value="high">高 (High)</option>
                  </select>
                  
                  <div style={{ marginTop: '12px' }}>
                    <label style={{ display: 'block', fontSize: '13px', marginBottom: '8px' }}>逐页丰富度覆盖</label>
                    <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '8px' }}>
                      {pageRichnessList.map((richness, index) => (
                        <div key={index} style={{ minWidth: '80px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>第 {index + 1} 页</span>
                          <select 
                            value={richness} 
                            onChange={(e) => {
                              const newList = [...pageRichnessList];
                              newList[index] = e.target.value;
                              setPageRichnessList(newList);
                            }} 
                            style={{ width: '100%', padding: '6px', borderRadius: '6px', border: '1px solid var(--border-light)', background: 'var(--bg-app)', fontSize: '12px' }}
                          >
                            <option value="">(默认)</option>
                            <option value="low">低</option>
                            <option value="medium">中</option>
                            <option value="high">高</option>
                          </select>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div style={{ border: '1px solid var(--border-light)', borderRadius: '16px', background: 'var(--bg-card)' }}>
        <CardHeader 
          title="风格约束" 
          description="参考风格图与风格补充会一起进入规划链路。"
          icon={ImageIcon}
          isOpen={openSections.includes('style')}
          onToggle={() => toggleSection('style')}
        />
        <AnimatePresence>
          {openSections.includes('style') && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              style={{ overflow: 'hidden' }}
            >
              <div style={{ padding: '20px', display: 'grid', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px' }}>风格补充</label>
                  <input type="text" value={styleNotes} onChange={(e) => setStyleNotes(e.target.value)} placeholder="例如：蓝白科技线稿、低透明..." style={{
                    width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', background: 'var(--bg-app)'
                  }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px' }}>参考风格图约束强度</label>
                  <select value={referenceStyleAdherence} onChange={(e) => setReferenceStyleAdherence(e.target.value)} required style={{
                    width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', background: 'var(--bg-app)'
                  }}>
                    {referenceStyleAdherenceOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px' }}>上传参考风格图 (可选)</label>
                  <input 
                    type="file" 
                    name="style_images" 
                    multiple 
                    accept="image/*"
                    onChange={(e) => {
                      const files = Array.from(e.target.files);
                      const urls = files.map(f => URL.createObjectURL(f));
                      setStylePreviewUrls(urls);
                    }}
                    style={{
                      width: '100%', padding: '8px', borderRadius: '8px', border: '1px dashed var(--border-light)', background: 'var(--bg-app)', fontSize: '13px'
                    }} 
                  />
                  {stylePreviewUrls.length > 0 && (
                    <div style={{ display: 'flex', gap: '8px', marginTop: '12px', overflowX: 'auto', paddingBottom: '4px' }}>
                      {stylePreviewUrls.map((url, i) => (
                        <img key={i} src={url} alt="预览" style={{ width: '60px', height: '60px', objectFit: 'cover', borderRadius: '8px', border: '1px solid var(--border-light)' }} />
                      ))}
                    </div>
                  )}
                  {stylePreviewUrls.length === 0 && currentJob?.job_meta?.style_reference_images?.length > 0 && (
                    <div style={{ display: 'flex', gap: '8px', marginTop: '12px', overflowX: 'auto', paddingBottom: '4px' }}>
                      {currentJob.job_meta.style_reference_images.map((img, i) => (
                        <img key={i} src={img.url} alt="历史预览" style={{ width: '60px', height: '60px', objectFit: 'cover', borderRadius: '8px', border: '1px solid var(--border-light)' }} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <motion.button 
        type="submit" 
        disabled={submitting} 
        className="btn btn-primary" 
        style={{ padding: '14px', fontSize: '16px' }}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.98 }}
      >
        {submitting ? '提交中...' : (currentJob ? '按当前参数重新生成' : '创建并生成任务')}
      </motion.button>
    </form>
  );
};

export default TaskConfigForm;
