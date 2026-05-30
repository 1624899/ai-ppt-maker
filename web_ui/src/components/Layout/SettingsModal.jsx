import { motion, AnimatePresence } from 'framer-motion';
import { useConfig } from '../../hooks/useConfig';
import { Loader2 } from 'lucide-react';

const SettingsModal = ({ isOpen, onClose }) => {
  const { config, loading } = useConfig();
  
  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div 
          initial={{ opacity: 0 }} 
          animate={{ opacity: 1 }} 
          exit={{ opacity: 0 }}
          style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px' }}
        >
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)' }} onClick={onClose} />
          <motion.div 
            initial={{ scale: 0.95, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: 20 }}
            style={{
              width: '100%', maxWidth: '600px', background: 'var(--bg-card)', 
              borderRadius: '24px', position: 'relative', display: 'flex', flexDirection: 'column',
              boxShadow: 'var(--shadow-lg)', overflow: 'hidden', border: '1px solid var(--border-light)'
            }}
          >
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '18px' }}>系统设置</h3>
                <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-muted)' }}>全局配置概览 (通过修改 config.yaml 并重启服务端生效)</p>
              </div>
              <button type="button" className="btn-icon" onClick={onClose}>×</button>
            </div>
            <div style={{ padding: '24px', flex: 1, display: 'flex', flexDirection: 'column', gap: '16px', background: 'var(--bg-app)', maxHeight: '60vh', overflowY: 'auto' }}>
              {loading ? (
                <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <Loader2 className="spin" size={24} style={{ margin: '0 auto' }} />
                </div>
              ) : config ? (
                <div style={{ display: 'grid', gap: '12px' }}>
                  <div style={{ padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: '8px', border: '1px solid var(--border-light)' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>最大允许生成页数</div>
                    <div style={{ fontSize: '14px', fontWeight: '500' }}>{config.max_pages} 页</div>
                  </div>
                  <div style={{ padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: '8px', border: '1px solid var(--border-light)' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>默认生成页数</div>
                    <div style={{ fontSize: '14px', fontWeight: '500' }}>{config.default_pages} 页</div>
                  </div>
                  <div style={{ padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: '8px', border: '1px solid var(--border-light)' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>默认画幅</div>
                    <div style={{ fontSize: '14px', fontWeight: '500' }}>{config.default_image_preset}</div>
                  </div>
                  <div style={{ padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: '8px', border: '1px solid var(--border-light)' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>任务输出目录</div>
                    <div style={{ fontSize: '14px', fontWeight: '500', fontFamily: 'monospace' }}>{config.output_dir}</div>
                  </div>
                </div>
              ) : (
                <div style={{ color: 'var(--danger)', textAlign: 'center', padding: '32px' }}>获取配置失败</div>
              )}
            </div>
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'flex-end', background: 'var(--bg-elevated)' }}>
              <button type="button" className="btn btn-primary" onClick={onClose}>确定</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default SettingsModal;
