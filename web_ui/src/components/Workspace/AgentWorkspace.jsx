import { useState } from 'react';
import { Bot, History, LoaderCircle, MessageSquareText, SlidersHorizontal, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import AgentChatPanel from './AgentChatPanel';
import CreationForm from './CreationForm';
import FeaturePending from './FeaturePending';
import StageProgress from './StageProgress';
import { useJobActions } from '../../hooks/useJobActions';
import {
  buildAgentSummary,
  getLatestPageVersion,
  getJobMeta,
  getOperationExecutionLabel,
  getJobPages,
  getJobTitle,
  getOperationStatusLabel,
  getPageSummary,
  getPageTitle,
  getRecentJobOperations,
  getStatusLabel,
} from '../../utils/jobPresentation';

const QUICK_ACTIONS = ['优化当前页', '减少文字', '增强视觉', '统一风格'];

const STYLE_OPTIONS = ['蓝白科技风', '深色科技风', '极简商务风'];
const LAYOUT_OPTIONS = ['更紧凑', '更留白', '改为三栏', '改为流程图'];

const QUICK_ACTION_OPERATION = {
  优化当前页: 'page_text_optimize',
  减少文字: 'page_text_optimize',
  增强视觉: 'page_layout_optimize',
  统一风格: 'job_style_adjust',
};

const AgentWorkspace = ({
  currentJob,
  selectedPageIndex,
  selectedPreviewType,
  imageAnnotations,
  onSelectPage,
  onJobCreated,
  onJobUpdated,
  onOpenImageMarkup,
}) => {
  const [mode, setMode] = useState('chat');
  const [draftInstruction, setDraftInstruction] = useState('');
  const [agentDraft, setAgentDraft] = useState(null);
  const pages = getJobPages(currentJob);
  const activePage = pages[selectedPageIndex] || pages[0];
  const meta = getJobMeta(currentJob);
  const agentSummary = buildAgentSummary(currentJob);
  const latestVersion = activePage ? getLatestPageVersion(currentJob, activePage.page_no) : null;
  const recentOperations = getRecentJobOperations(currentJob);
  const isRunning = ['queued', 'running', 'stopping'].includes(String(currentJob?.status || ''));
  const { pendingKey, error: actionError, runOperation } = useJobActions({ currentJob, onJobUpdated });

  const submitOperation = async (operationType, fallbackInstruction = '', instructionOverride = null) => {
    const instruction = String(instructionOverride ?? (draftInstruction || fallbackInstruction)).trim();
    const pageNo = activePage?.page_no;
    const pageScoped = operationType.startsWith('page_') || operationType === 'restore_page_version';
    const payload = {
      operation_type: operationType,
      instruction,
      source: mode,
    };
    if (pageScoped && pageNo) payload.page_no = pageNo;
    if (operationType === 'restore_page_version' && latestVersion?.version_id) {
      payload.version_id = latestVersion.version_id;
    }
    const result = await runOperation(payload, { key: operationType });
    if (result && operationType !== 'restore_page_version') {
      setDraftInstruction('');
    }
  };

  const quickSubmit = async (action) => {
    const operationType = QUICK_ACTION_OPERATION[action];
    if (!operationType) return;
    const prefix = activePage && operationType !== 'job_style_adjust' ? `第 ${activePage.page_no} 页` : '整套 PPT';
    const instruction = draftInstruction.trim() || `${prefix}${action}`;
    setDraftInstruction(instruction);
    await submitOperation(operationType, instruction, instruction);
    if (activePage && operationType !== 'job_style_adjust') setMode('edit');
  };

  const confirmAgentDraft = (draft) => {
    setAgentDraft(draft);
    if (typeof draft?.page_no === 'number') {
      const pageIndex = pages.findIndex((page) => Number(page.page_no) === Number(draft.page_no));
      if (pageIndex >= 0) onSelectPage(pageIndex);
    }
    setMode('edit');
  };

  const submitDraftOperation = async (fallbackOperationType) => {
    const operationType = agentDraft?.operation_type || fallbackOperationType;
    await submitOperation(operationType, draftInstruction);
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
                <div className="quick-actions" aria-label="快捷修改">
                  {QUICK_ACTIONS.map((action) => (
                    <button
                      type="button"
                      key={action}
                      onClick={() => quickSubmit(action)}
                      disabled={pendingKey !== '' || (isRunning && action !== '导出PPT')}
                      title={action === '导出PPT' ? '会先写入导出要求，请在右侧选择导出格式' : '提交 Agent 编辑操作'}
                    >
                      {pendingKey === QUICK_ACTION_OPERATION[action] ? '提交中...' : action}
                    </button>
                  ))}
                </div>
                <AgentChatPanel
                  key={currentJob.job_id}
                  currentJob={currentJob}
                  activePage={activePage}
                  previewType={selectedPreviewType}
                  annotations={imageAnnotations}
                  draftInstruction={draftInstruction}
                  onDraftInstructionChange={setDraftInstruction}
                  onDraftConfirmed={confirmAgentDraft}
                  onOpenImageMarkup={onOpenImageMarkup}
                />
                {actionError && <div className="form-error">{actionError}</div>}
                {recentOperations.length > 0 && (
                  <section className="operation-feed">
                    <div className="section-title">
                      <History size={15} />
                      <span>最近操作</span>
                    </div>
                    {recentOperations.map((operation) => (
                      <article className="operation-item" key={operation.operation_id}>
                        <strong>{operation.label || operation.type}</strong>
                        <span>
                          {[getOperationStatusLabel(operation.status), getOperationExecutionLabel(operation.execution)].filter(Boolean).join(' · ')}
                          {' · '}
                          {operation.message || operation.instruction || '已同步到任务状态'}
                        </span>
                      </article>
                    ))}
                  </section>
                )}
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

                <FeaturePending title="单页编辑已接入后端">
                  这里会承接 Agent 整理后的改动内容。确认提交后，文字优化会保留当前图片，排版/风格修改会备份页面并重跑相关产物。
                </FeaturePending>

                {agentDraft && (
                  <div className="agent-draft-strip">
                    <span>来自 Agent 对话</span>
                    <strong>{agentDraft.summary}</strong>
                  </div>
                )}

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
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => submitOperation('page_regenerate', `第 ${activePage.page_no} 页重新生成`)}
                    disabled={pendingKey !== '' || isRunning}
                  >
                    {pendingKey === 'page_regenerate' ? '提交中...' : '重新生成本页'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => submitDraftOperation('page_text_optimize')}
                    disabled={pendingKey !== '' || !draftInstruction.trim()}
                  >
                    {pendingKey === 'page_text_optimize' ? <LoaderCircle className="spin" size={16} /> : <MessageSquareText size={16} />}
                    仅优化文字
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => submitDraftOperation('page_layout_optimize')}
                    disabled={pendingKey !== '' || !draftInstruction.trim()}
                  >
                    仅优化排版
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => submitOperation('job_style_adjust', draftInstruction)}
                    disabled={pendingKey !== '' || !draftInstruction.trim()}
                  >
                    修改整套风格
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => submitOperation('restore_page_version', `恢复第 ${activePage.page_no} 页上一版`)}
                    disabled={pendingKey !== '' || isRunning || !latestVersion}
                    title={latestVersion ? `恢复版本 ${latestVersion.version_id}` : '重新生成后才会产生可恢复版本'}
                  >
                    恢复上一版
                  </button>
                </div>
                {actionError && <div className="form-error">{actionError}</div>}
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
