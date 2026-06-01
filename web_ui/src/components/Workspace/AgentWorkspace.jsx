import { useState } from 'react';
import { Bot, CheckCircle2, History, LoaderCircle, MessageSquareText, MousePointer2, SlidersHorizontal, Sparkles, WandSparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import { StaggerContainer, StaggerItem, ScaleButton } from '../Motion/MotionUI';
import AgentChatPanel from './AgentChatPanel';
import CreationForm from './CreationForm';
import SlideImage from './SlideImage';
import StageProgress from './StageProgress';
import { applyImageEditCandidate, postImageEditCandidate } from '../../utils/jobActions';
import { getLatestImageEditCandidate, isImageEditCandidateApplied } from '../../utils/imageEditCandidates';
import {
  buildAgentSummary,
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
  const recentOperations = getRecentJobOperations(currentJob);
  const isRunning = ['queued', 'running', 'stopping'].includes(String(currentJob?.status || ''));
  const [imageEditPending, setImageEditPending] = useState('');
  const [imageEditError, setImageEditError] = useState('');
  const latestCandidate = activePage
    ? getLatestImageEditCandidate(currentJob, activePage.page_no, selectedPreviewType)
    : null;
  const activePreviewLabel = selectedPreviewType === 'element' ? '元素图' : selectedPreviewType === 'preview' ? '预览图' : '原稿图';

  const confirmAgentDraft = (draft) => {
    setAgentDraft(draft);
    if (typeof draft?.page_no === 'number') {
      const pageIndex = pages.findIndex((page) => Number(page.page_no) === Number(draft.page_no));
      if (pageIndex >= 0) onSelectPage(pageIndex);
    }
    setMode('edit');
  };

  const generateImageEditCandidate = async () => {
    if (!currentJob?.job_id || !activePage || imageEditPending) return;
    const instruction = String(draftInstruction || '').trim();
    if (!instruction) {
      setImageEditError('请先填写文字描述调整。');
      return;
    }
    setImageEditPending('generate');
    setImageEditError('');
    try {
      const updatedJob = await postImageEditCandidate(currentJob.job_id, {
        page_no: activePage.page_no,
        preview_type: selectedPreviewType,
        instruction,
        annotations: imageAnnotations,
      });
      onJobUpdated?.(updatedJob);
    } catch (err) {
      setImageEditError(err.message || '生成编辑预览失败');
    } finally {
      setImageEditPending('');
    }
  };

  const applyLatestCandidate = async () => {
    if (!currentJob?.job_id || !latestCandidate?.candidate_id || imageEditPending) return;
    setImageEditPending('apply');
    setImageEditError('');
    try {
      const updatedJob = await applyImageEditCandidate(currentJob.job_id, latestCandidate.candidate_id);
      onJobUpdated?.(updatedJob);
    } catch (err) {
      setImageEditError(err.message || '替换原图失败');
    } finally {
      setImageEditPending('');
    }
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
          <ScaleButton className={clsx(mode === 'chat' && 'is-active')} onClick={() => setMode('chat')}>
            <MessageSquareText size={16} />
            对话
          </ScaleButton>
          <ScaleButton className={clsx(mode === 'edit' && 'is-active')} onClick={() => setMode('edit')} disabled={!activePage}>
            <SlidersHorizontal size={16} />
            编辑
          </ScaleButton>
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
              <StaggerContainer className="page-outline" itemCount={pages.length}>
                {pages.map((page, index) => {
                  const selected = index === selectedPageIndex;
                  return (
                    <StaggerItem key={page.page_no}>
                      <ScaleButton
                        className={clsx(selected && 'is-active')}
                        aria-pressed={selected}
                        onClick={() => onSelectPage(index)}
                      >
                        <span>{page.page_no}</span>
                        {getPageTitle(page)}
                      </ScaleButton>
                    </StaggerItem>
                  );
                })}
              </StaggerContainer>
            )}
          </div>
        </section>

        <AnimatePresence mode="wait">
          {mode === 'chat' ? (
            <motion.section 
              key="chat"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="chat-stage"
            >
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
                <AgentChatPanel
                  key={currentJob.job_id}
                  currentJob={currentJob}
                  activePage={activePage}
                  previewType={selectedPreviewType}
                  annotations={imageAnnotations}
                  draftInstruction={draftInstruction}
                  onDraftInstructionChange={setDraftInstruction}
                  onDraftConfirmed={confirmAgentDraft}
                  onConversationCleared={(updatedJob) => {
                    setAgentDraft(null);
                    if (updatedJob?.job_id) onJobUpdated(updatedJob);
                  }}
                  onOpenImageMarkup={onOpenImageMarkup}
                />
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
            </motion.section>
          ) : (
            <motion.section 
              key="edit"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="edit-stage"
            >
            {activePage ? (
              <>
                <div className="edit-stage__title">
                  <span>正在编辑：第 {activePage.page_no} 页</span>
                  <h3>{getPageTitle(activePage)}</h3>
                  {getPageSummary(activePage) && <p>{getPageSummary(activePage)}</p>}
                </div>

                {agentDraft && (
                  <div className="agent-draft-strip">
                    <span>来自 Agent 对话</span>
                    <strong>{agentDraft.summary}</strong>
                  </div>
                )}

                <div className="edit-block">
                  <span>文字描述调整</span>
                  <label>
                    修改要求
                    <textarea
                      value={draftInstruction}
                      onChange={(event) => setDraftInstruction(event.target.value)}
                      placeholder={`描述第 ${activePage.page_no} 页要怎么改，例如：右侧模块更清晰，主标题更短，整体更像咨询汇报...`}
                    />
                  </label>
                </div>

                <div className="edit-block">
                  <span>标注编辑预览</span>
                  {imageAnnotations?.length ? (
                    <div className="annotation-preview-list">
                      {imageAnnotations.map((annotation, index) => (
                        <span key={annotation.id || `${annotation.label}-${index}`}>
                          {annotation.label || `区域 ${index + 1}`}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="annotation-preview-empty">当前没有框选标注，将只按文字描述编辑。</div>
                  )}
                  <ScaleButton className="btn btn-secondary edit-stage__markup-button ai-glow-button" onClick={onOpenImageMarkup}>
                    <MousePointer2 size={16} />
                    标注编辑
                  </ScaleButton>
                </div>

                <div className="edit-block image-edit-preview">
                  <div className="image-edit-preview__head">
                    <span>编辑生成预览</span>
                    {latestCandidate && (
                      <strong>{isImageEditCandidateApplied(latestCandidate) ? '已替换' : '待确认替换'}</strong>
                    )}
                  </div>
                  <SlideImage
                    src={latestCandidate?.image || ''}
                    alt={latestCandidate ? `第 ${activePage.page_no} 页编辑预览` : '编辑生成预览'}
                    loading={imageEditPending === 'generate'}
                    emptyTitle={imageEditPending === 'generate' ? '正在生成预览' : '等待编辑生成'}
                    emptyDescription={`会基于当前${activePreviewLabel}、修改要求和可选标注生成一张新图。`}
                    sourceLabel={latestCandidate?.preview_label || activePreviewLabel}
                    showMeta
                  />
                  {latestCandidate?.instruction && (
                    <p className="image-edit-preview__instruction">{latestCandidate.instruction}</p>
                  )}
                </div>

                <div className="edit-actions">
                  <ScaleButton
                    className="btn btn-primary ai-glow-button"
                    onClick={generateImageEditCandidate}
                    disabled={imageEditPending !== '' || isRunning || !draftInstruction.trim()}
                  >
                    {imageEditPending === 'generate' ? <LoaderCircle className="spin" size={16} /> : <WandSparkles size={16} />}
                    重新生成预览
                  </ScaleButton>
                  <ScaleButton
                    className="btn btn-secondary"
                    onClick={applyLatestCandidate}
                    disabled={imageEditPending !== '' || !latestCandidate || isImageEditCandidateApplied(latestCandidate)}
                  >
                    {imageEditPending === 'apply' ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}
                    替换原图
                  </ScaleButton>
                </div>
                {imageEditError && <div className="form-error">{imageEditError}</div>}
              </>
            ) : (
              <div className="empty-state">右侧选择一页后，这里会显示该页编辑属性。</div>
            )}
            </motion.section>
          )}
        </AnimatePresence>
      </div>
    </main>
  );
};

export default AgentWorkspace;
