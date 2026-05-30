import TaskConfigForm from '../Forms/TaskConfigForm';

const MainPanel = ({ currentJob }) => {
  return (
    <section className="glass" style={{
      display: 'grid',
      gridTemplateRows: 'auto minmax(0, 1fr)',
      borderRadius: '24px',
      overflow: 'hidden'
    }}>
      <div style={{
        padding: '24px',
        borderBottom: '1px solid var(--border-light)'
      }}>
        <h2 style={{ fontSize: '18px', marginBottom: '8px' }}>参数</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
          这里显示当前任务的内容与生成参数。
        </p>
      </div>
      
      <div style={{ padding: '24px', overflowY: 'auto' }}>
        <TaskConfigForm currentJob={currentJob} />
      </div>
    </section>
  );
};

export default MainPanel;
