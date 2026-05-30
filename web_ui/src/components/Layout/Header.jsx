import { useState } from 'react';
import { Plus, Settings } from 'lucide-react';
import SettingsModal from './SettingsModal';
import { getJobTitle, getStatusLabel } from '../../utils/jobPresentation';

const Header = ({ currentJob, onCreateTask }) => {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <>
      <header className="app-topbar">
        <div className="brand-block">
          <div className="brand-mark">
            P
          </div>
          <div>
            <h1>PPT 制作系统</h1>
            <p>任务中心 | 创作工作区 | PPT Studio</p>
          </div>
        </div>

        <div className="topbar-task">
          <span>当前任务</span>
          <strong>{currentJob ? getJobTitle(currentJob) : '准备创建新任务'}</strong>
          <em>{currentJob ? getStatusLabel(currentJob.status) : '未开始'}</em>
        </div>

        <div className="topbar-actions">
          <button className="btn btn-secondary" onClick={() => setIsSettingsOpen(true)}>
            <Settings size={18} />
            <span>设置</span>
          </button>
          <button className="btn btn-primary" onClick={onCreateTask}>
            <Plus size={18} />
            <span>创建任务</span>
          </button>
        </div>
      </header>
      
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </>
  );
};

export default Header;
