import { PlusCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import { useJobs } from '../../hooks/useJobs';

const Sidebar = ({ currentJob, onSelectJob }) => {
  const { jobs, loading } = useJobs();

  return (
    <aside className="glass" style={{
      display: 'grid',
      gridTemplateRows: 'auto minmax(0, 1fr)',
      borderRadius: '24px',
      overflow: 'hidden'
    }}>
      <div style={{
        padding: '24px',
        borderBottom: '1px solid var(--border-light)'
      }}>
        <h2 style={{ fontSize: '18px', marginBottom: '8px' }}>历史任务</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
          每条任务都保留自己的参数与输出结果。
        </p>
      </div>
      
      <div style={{ padding: '16px', overflowY: 'auto' }}>
        <button 
          className="btn btn-secondary" 
          style={{ width: '100%', marginBottom: '16px', justifyContent: 'flex-start', padding: '12px 16px' }}
          onClick={() => onSelectJob(null)}
        >
          <PlusCircle size={18} style={{ color: 'var(--primary)' }} />
          <span>开启新任务</span>
          <span style={{ marginLeft: 'auto', fontSize: '12px', color: 'var(--text-muted)' }}>Ctrl+J</span>
        </button>

        <div style={{ display: 'grid', gap: '12px' }}>
          {loading ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '14px', textAlign: 'center' }}>加载中...</div>
          ) : jobs.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '14px', textAlign: 'center' }}>暂无历史任务</div>
          ) : (
            <motion.div
              initial="hidden"
              animate="show"
              variants={{
                hidden: { opacity: 0 },
                show: {
                  opacity: 1,
                  transition: { staggerChildren: 0.05 }
                }
              }}
              style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}
            >
              {jobs.map(job => {
                const isActive = currentJob?.job_id === job.job_id;
                return (
                  <motion.div 
                    key={job.job_id}
                    variants={{
                      hidden: { opacity: 0, y: 15 },
                      show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 24 } }
                    }}
                    whileHover={{ scale: 1.01, y: -2 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => onSelectJob(job)}
                    style={{
                      padding: '16px',
                      borderRadius: '12px',
                      background: isActive ? 'var(--primary)' : 'var(--bg-card)',
                      color: isActive ? '#fff' : 'inherit',
                      border: `1px solid ${isActive ? 'var(--primary)' : 'transparent'}`,
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                      boxShadow: isActive ? 'var(--shadow-btn)' : 'var(--shadow-sm)',
                      transition: 'background 0.2s, border 0.2s, color 0.2s'
                    }}
                  >
                    <h4 style={{ margin: 0, fontSize: '14px', fontWeight: '500', color: isActive ? '#fff' : 'var(--text-main)', lineHeight: '1.4' }}>
                      {job.title ? `${job.title.substring(0, 30)}${job.title.length > 30 ? '...' : ''}` : '未命名任务'}
                    </h4>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '12px', color: isActive ? 'rgba(255,255,255,0.8)' : 'var(--text-muted)' }}>
                        {job.status === 'completed' ? '已完成' : job.status === 'running' ? '处理中' : '等待中'}
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </motion.div>
          )}
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
