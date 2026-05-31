import { useState } from 'react';
import { Play, Square, CheckCircle2, Loader2, AlertCircle, Download } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const STAGES_DEF = [
  { key: 'queued', label: '等待执行' },
  { key: 'planning', label: '模型规划' },
  { key: 'reference_generation', label: '原稿图生成' },
  { key: 'elements_generation', label: '元素图生成' },
  { key: 'ppt_export', label: '可编辑元素生成' },
  { key: 'completed', label: '全部完成' }
];

const StageTimeline = ({ currentStage, status, stagesData, onStageClick }) => {
  const currentIndex = STAGES_DEF.findIndex(s => s.key === currentStage);
  
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', position: 'relative' }}>
      <div style={{ position: 'absolute', top: '14px', left: '20px', right: '20px', height: '2px', background: 'var(--border-light)', zIndex: 0 }} />
      <motion.div 
        initial={{ width: 0 }}
        animate={{ width: `${Math.max(0, (currentIndex / (STAGES_DEF.length - 1)) * 100)}%` }}
        transition={{ duration: 0.5 }}
        style={{ position: 'absolute', top: '14px', left: '20px', height: '2px', background: 'var(--primary)', zIndex: 0 }}
      />
      
      {STAGES_DEF.map((stageDef, idx) => {
        const isPast = idx < currentIndex;
        const isCurrent = idx === currentIndex;
        
        // Find stage data if available
        const stageData = stagesData?.find(s => s.key === stageDef.key);
        const stageStatus = stageData ? stageData.status : (isCurrent ? status : (isPast ? 'completed' : 'pending'));
        const isError = stageStatus === 'error' || (isCurrent && status === 'error');
        
        let bgColor = 'var(--bg-elevated)';
        let borderColor = 'var(--border-light)';
        let color = 'var(--text-muted)';
        
        if (stageStatus === 'completed' || isPast) {
          bgColor = 'var(--success)';
          borderColor = 'var(--success)';
          color = '#fff';
        } else if (stageStatus === 'running' || (isCurrent && status === 'running')) {
          bgColor = '#fff';
          borderColor = 'var(--primary)';
          color = 'var(--primary)';
        } else if (isError) {
          bgColor = 'var(--danger)';
          borderColor = 'var(--danger)';
          color = '#fff';
        }

        return (
          <div key={stageDef.key} onClick={() => onStageClick(stageDef.key, stageData)} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', zIndex: 1, background: 'var(--bg-elevated)', padding: '0 8px', cursor: 'pointer' }}>
            <motion.div 
              animate={{ 
                scale: stageStatus === 'running' ? [1, 1.15, 1] : 1,
                boxShadow: stageStatus === 'running' ? ['0 0 0 0 rgba(31,94,255,0)', '0 0 0 8px rgba(31,94,255,0.2)', '0 0 0 0 rgba(31,94,255,0)'] : 'none'
              }}
              whileHover={{ scale: 1.1 }}
              transition={{ repeat: stageStatus === 'running' ? Infinity : 0, duration: 2, ease: "easeInOut" }}
              style={{
                width: '32px', height: '32px', borderRadius: '50%',
                display: 'grid', placeItems: 'center',
                background: bgColor, border: `2px solid ${borderColor}`, color
              }}
            >
              {stageStatus === 'completed' || isPast ? <CheckCircle2 size={16} /> : 
               isError ? <AlertCircle size={16} /> : 
               stageStatus === 'running' ? <Loader2 size={14} className="spin" /> : 
               <span style={{ fontSize: '12px', fontWeight: '500' }}>{idx + 1}</span>}
            </motion.div>
            <span style={{ fontSize: '12px', fontWeight: isCurrent ? '600' : '400', color: isCurrent ? 'var(--text-main)' : 'var(--text-muted)' }}>
              {stageDef.label}
            </span>
          </div>
        );
      })}
    </div>
  );
};

const ResultPanel = ({ currentJob }) => {
  const [selectedPage, setSelectedPage] = useState(0);
  const [activeStageLogs, setActiveStageLogs] = useState(null);

  const pages = currentJob?.pages || [];
  const activePage = pages[selectedPage];
  const actions = currentJob?.delivery_actions || [];

  return (
    <section className="glass" style={{
      display: 'grid',
      gridTemplateRows: 'auto minmax(0, 1fr)',
      borderRadius: '24px',
      overflow: 'hidden',
      background: 'var(--bg-elevated)'
    }}>
      <div style={{
        padding: '24px',
        borderBottom: '1px solid var(--border-light)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between'
      }}>
        <div>
          <h2 style={{ fontSize: '18px', marginBottom: '8px' }}>生成结果</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
            {currentJob ? `任务 ${currentJob.job_id} - ${currentJob.title || '未命名任务'}` : '等待提交任务'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {currentJob && (currentJob.status === 'running' || currentJob.status === 'queued') && (
            <button className="btn btn-secondary" style={{ padding: '8px 12px' }}>
              <Square size={16} /> 停止
            </button>
          )}
          {currentJob && currentJob.status === 'interrupted' && (
            <button className="btn btn-secondary" style={{ padding: '8px 12px' }}>
              <Play size={16} /> 继续生成
            </button>
          )}
          {actions.map(action => {
            if (action.generated && action.generated_file?.pptx_url) {
              return (
                <a key={action.key} href={action.generated_file.pptx_url} download className="btn btn-primary" style={{ padding: '8px 16px', textDecoration: 'none' }}>
                  <Download size={16} /> 下载 {action.label}
                </a>
              );
            }
            return null;
          })}
        </div>
      </div>
      
      <div style={{ padding: '32px', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        {currentJob ? (
          <>
            <StageTimeline 
              currentStage={currentJob.current_stage || 'queued'} 
              status={currentJob.status || 'queued'} 
              stagesData={currentJob.stages} 
              onStageClick={(key, data) => {
                if (data) setActiveStageLogs(data);
              }}
            />
            
            <AnimatePresence mode="wait">
              {pages.length > 0 && activePage ? (
                <motion.div
                  key="gallery"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}
                >
                  <div style={{
                    width: '100%',
                    aspectRatio: '16/9',
                    background: 'var(--bg-app)',
                    borderRadius: '16px',
                    border: '1px solid var(--border-light)',
                    display: 'grid',
                    placeItems: 'center',
                    overflow: 'hidden',
                    position: 'relative'
                  }}>
                    {activePage.element_image || activePage.reference_image ? (
                      <img src={activePage.element_image || activePage.reference_image} alt={`Slide ${activePage.page_no}`} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                    ) : (
                      <div style={{ color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                        {activePage.status === 'pending' || activePage.status === 'running' ? (
                          <>
                            <Loader2 size={32} className="spin" />
                            <span>生成中... ({activePage.title})</span>
                          </>
                        ) : (
                          <span>准备中...</span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Thumbnail Strip */}
                  <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '8px' }}>
                    {pages.map((p, idx) => {
                      const imgUrl = p.element_image || p.reference_image;
                      return (
                        <div 
                          key={p.page_no}
                          onClick={() => setSelectedPage(idx)}
                          style={{
                            width: '120px', minWidth: '120px', aspectRatio: '16/9', borderRadius: '8px',
                            border: `2px solid ${idx === selectedPage ? 'var(--primary)' : 'transparent'}`,
                            background: 'var(--bg-card)', overflow: 'hidden', cursor: 'pointer',
                            display: 'grid', placeItems: 'center', color: 'var(--text-muted)'
                          }}
                        >
                          {imgUrl ? (
                            <img src={imgUrl} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <span style={{ fontSize: '12px' }}>{p.page_no}</span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </motion.div>
              ) : (
                <motion.div 
                  key="placeholder"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  style={{
                    width: '100%',
                    aspectRatio: '16/9',
                    background: 'var(--bg-app)',
                    borderRadius: '16px',
                    border: '1px solid var(--border-light)',
                    display: 'grid',
                    placeItems: 'center',
                    marginTop: '16px'
                  }}
                >
                  <div style={{ color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                    <Loader2 size={32} className="spin" />
                    <span>正在准备生成任务，请稍候...</span>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{
              width: '100%',
              maxWidth: '800px',
              aspectRatio: '16/9',
              background: 'var(--bg-app)',
              borderRadius: '16px',
              border: '2px dashed var(--border-light)',
              display: 'grid',
              placeItems: 'center',
              color: 'var(--text-muted)'
            }}>
              等待生成
            </div>
          </div>
        )}
      </div>

      {/* Stage Logs Modal */}
      <AnimatePresence>
        {activeStageLogs && (
          <motion.div 
            initial={{ opacity: 0 }} 
            animate={{ opacity: 1 }} 
            exit={{ opacity: 0 }}
            style={{ position: 'fixed', inset: 0, zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px' }}
          >
            <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)' }} onClick={() => setActiveStageLogs(null)} />
            <motion.div 
              initial={{ scale: 0.95, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.95, y: 20 }}
              style={{
                width: '100%', maxWidth: '800px', height: '70vh', background: 'var(--bg-card)', 
                borderRadius: '24px', position: 'relative', display: 'flex', flexDirection: 'column',
                boxShadow: 'var(--shadow-lg)', overflow: 'hidden', border: '1px solid var(--border-light)'
              }}
            >
              <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: '18px' }}>{activeStageLogs.label} - 任务流</h3>
                  <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-muted)' }}>{activeStageLogs.summary}</p>
                </div>
                <button type="button" className="btn-icon" onClick={() => setActiveStageLogs(null)}>×</button>
              </div>
              <div style={{ padding: '24px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '8px', background: 'var(--bg-app)' }}>
                {activeStageLogs.logs && activeStageLogs.logs.length > 0 ? (
                  activeStageLogs.logs.map((log, idx) => (
                    <div key={idx} style={{ 
                      padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: '8px', border: '1px solid var(--border-light)',
                      fontSize: '13px', fontFamily: 'monospace', color: 'var(--text-main)', whiteSpace: 'pre-wrap'
                    }}>
                      {log}
                    </div>
                  ))
                ) : (
                  <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '32px' }}>暂无日志记录</div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
};

export default ResultPanel;
