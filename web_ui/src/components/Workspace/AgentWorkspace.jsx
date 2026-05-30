import { useState } from 'react';
import { Bot, Lock, MessageSquareText, PanelTopOpen, SlidersHorizontal, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import CreationForm from './CreationForm';
import FeaturePending from './FeaturePending';
import StageProgress from './StageProgress';
import {
  buildAgentSummary,
  getJobMeta,
  getJobPages,
  getJobTitle,
  getPageSummary,
  getPageTitle,
  getStatusLabel,
} from '../../utils/jobPresentation';

const QUICK_ACTIONS = ['优化当前页', '减少文字', '增强视觉', '统一风格', '导出PPT'];

const STYLE_OPTIONS = ['蓝白科技风', '深色科技风', '极简商务风'];
const LAYOUT_OPTIONS = ['更紧凑', '更留白', '改为三栏', '改为流程图'];

const AgentWorkspace = ({ currentJob, selectedPageIndex, onSelectPage, onJobCreated }) => {
  const [mode, setMode] = useState('chat');
  const [draftInstruction, setDraftInstruction] = useState('');
  const pages = getJobPages(currentJob);
  const activePage = pages[selectedPageIndex] || pages[0];
  const meta = getJobMeta(currentJob);
  const agentSummary = buildAgentSummary(currentJob);

  const pushQuickAction = (action) => {
    if (action === '导出PPT') {
      setDraftInstruction('请导出当前 PPT，并优先生成可编辑 PPTX。');
      return;
    }
    setDraftInstruction((value) => {
      const prefix = activePage ? `第 ${activePage.page_no} 页` : '整套 PPT';
      return value ? `${value}；${prefix}${action}` : `${prefix}${action}`;
    });
    if (activePage) setMode('edit');
  };

  return (
    <main className="workspace-panel agent-workspace">
      <div className="workspace-panel__header agent-workspace__header">
        <div>
          <span className="eyebrow">创作工作区</span>
          <h2>{currentJob ? getJobTitle(currentJob) : '创建你的下一份 PPT'}</h2>
          <p>{currentJob ? `${getStatusLabel(currentJob.status)} · ${meta.job_target_label || '可编辑 PPT'}` : '先描述目标，Agent 会生成初稿并持续接受修改。'}</p>
        </div>
        <div className="mode-switch" role="tablist" aria-label="工作模式">
          <button type="button" className={clsx(mode === 'chat' && 'is-active')} onClick={() => setMode('chat')}>
            <MessageSquareText size={16} />
            对话
          </button>
          <button type="button" className={clsx(mode === 'edit' && 'is-active')} onClick={() => setMode('edit')} disabled={!activePage}>
            <SlidersHorizontal size={16} />
            编辑
          </button>
        </div>
      </div>

      <div className="agent-workspace__body">
        {currentJob && <StageProgress job={currentJob} dense />}

        <section className="agent-card agent-card--hero">
          <div className="agent-avatar">
            <Bot size={22} />
          </div>
          <div>
            <span className="agent-card__label">Agent 反馈</span>
            <h3>{agentSummary.title}</h3>
            <p>{agentSummary.body}</p>
            {pages.length > 0 && (
              <ol className="page-outline">
                {pages.slice(0, 6).map((page, index) => (
                  <li key={page.page_no}>
                    <button type="button" onClick={() => {
                      onSelectPage(index);
                      setMode('edit');
                    }}>
                      <span>{page.page_no}</span>
                      {getPageTitle(page)}
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>

        {mode === 'chat' ? (
          <section className="chat-stage">
            {!currentJob && (
              <div className="agent-card">
                <div className="agent-card__title-row">
                  <Sparkles size={18} />
                  <h3>生成初稿</h3>
                </div>
                <CreationForm compact onCreated={onJobCreated} />
              </div>
            )}

            {currentJob && (
              <>
                <FeaturePending title="对话修改待后端接入">
                  当前可以先整理修改意图并切到编辑面板查看页面上下文；真正的 Agent 改稿、单页重做和版本恢复接口尚未实现。
                </FeaturePending>
                <div className="quick-actions quick-actions--pending" aria-label="待接入快捷修改">
                  {QUICK_ACTIONS.map((action) => (
                    <button
                      type="button"
                      key={action}
                      onClick={() => pushQuickAction(action)}
                      title="会先写入修改要求，暂不直接调用后端"
                    >
                      {action}
                    </button>
                  ))}
                </div>
                <div className="conversation-card">
                  <div className="message message--agent">
                    <strong>Agent</strong>
                    <p>你可以继续告诉我想怎么改：比如“第二页更商务一点”“第三页减少文字”“整体改成蓝白科技风”。</p>
                  </div>
                  <div className="composer">
                    <textarea
                      value={draftInstruction}
                      onChange={(event) => setDraftInstruction(event.target.value)}
                      placeholder="输入修改要求，例如：把第 3 页改成流程图风格..."
                    />
                    <button type="button" className="btn btn-primary" onClick={() => setMode(activePage ? 'edit' : 'chat')}>
                      <PanelTopOpen size={17} />
                      应用到编辑面板
                    </button>
                    <button type="button" className="btn btn-secondary" disabled title="Agent 对话修改接口尚未实现">
                      <Lock size={16} />
                      发送给 Agent
                    </button>
                  </div>
                </div>
                <details className="agent-card advanced-config">
                  <summary>需要重新生成整套 PPT？展开参数</summary>
                  <CreationForm compact currentJob={currentJob} onCreated={onJobCreated} />
                </details>
              </>
            )}
          </section>
        ) : (
          <section className="edit-stage">
            {activePage ? (
              <>
                <div className="edit-stage__title">
                  <span>正在编辑：第 {activePage.page_no} 页</span>
                  <h3>{getPageTitle(activePage)}</h3>
                  {getPageSummary(activePage) && <p>{getPageSummary(activePage)}</p>}
                </div>

                <FeaturePending title="单页编辑待后端接入">
                  下方控件用于确认交互形态和收集修改意图，暂不会触发真实重排、改稿或版本恢复。
                </FeaturePending>

                <div className="edit-block">
                  <span>页面风格</span>
                  <div className="chip-grid">
                    {STYLE_OPTIONS.map((option) => (
                      <button type="button" key={option} onClick={() => setDraftInstruction(`第 ${activePage.page_no} 页调整为${option}`)}>
                        {option}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="edit-block">
                  <span>文字调整</span>
                  <label>
                    标题
                    <input readOnly value={getPageTitle(activePage)} />
                  </label>
                  <label>
                    修改要求
                    <textarea
                      value={draftInstruction}
                      onChange={(event) => setDraftInstruction(event.target.value)}
                      placeholder="例如：标题更短，正文减少到 3 个要点..."
                    />
                  </label>
                </div>

                <div className="edit-block">
                  <span>布局调整</span>
                  <div className="chip-grid">
                    {LAYOUT_OPTIONS.map((option) => (
                      <button type="button" key={option} onClick={() => setDraftInstruction(`第 ${activePage.page_no} 页${option}`)}>
                        {option}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="edit-actions">
                  <button type="button" className="btn btn-primary" disabled>重新生成本页</button>
                  <button type="button" className="btn btn-secondary" disabled>仅优化文字</button>
                  <button type="button" className="btn btn-secondary" disabled>仅优化排版</button>
                  <button type="button" className="btn btn-secondary" disabled>恢复上一版</button>
                </div>
              </>
            ) : (
              <div className="empty-state">右侧选择一页后，这里会显示该页编辑属性。</div>
            )}
          </section>
        )}
      </div>
    </main>
  );
};

export default AgentWorkspace;
