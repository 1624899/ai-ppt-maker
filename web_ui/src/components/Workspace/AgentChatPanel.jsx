import { useState } from 'react';
import { Bot, CheckCircle2, LoaderCircle, MessageSquareText, MousePointer2, SendHorizontal, UserRound } from 'lucide-react';
import clsx from 'clsx';
import { useAgentDraft } from '../../hooks/useAgentDraft';
import { getPageTitle } from '../../utils/jobPresentation';

const WELCOME_MESSAGE = {
  id: 'welcome',
  role: 'assistant',
  message: '选中右侧原稿图后，可以用比较模糊的话告诉我哪里不对，比如“这里太挤”“这块层级不清楚”“右边图标换得更商务”。我会先整理成具体改动，等你确认后再带到编辑页。',
};

const QUICK_PROMPTS = ['这里有点乱', '层级不清楚', '文字太多', '视觉不够商务'];

const normalizeServerMessages = (messages) => {
  if (!Array.isArray(messages)) return [];
  return messages
    .filter((message) => message && ['user', 'assistant'].includes(String(message.role || '')))
    .map((message) => ({
      id: message.turn_id || `${message.role}-${message.created_at || Math.random()}`,
      role: message.role,
      message: message.message || message.content || '',
      draft: message.draft || null,
    }))
    .filter((message) => message.message);
};

const buildClientContext = (messages) => messages
  .filter((message) => message.role === 'user' || message.role === 'assistant')
  .slice(-8)
  .map((message) => ({
    role: message.role,
    message: message.message,
  }));

const AgentChatPanel = ({
  currentJob,
  activePage,
  previewType,
  annotations,
  draftInstruction,
  onDraftInstructionChange,
  onDraftConfirmed,
  onOpenImageMarkup,
}) => {
  const [messages, setMessages] = useState(() => normalizeServerMessages(currentJob?.agent_conversation));
  const [input, setInput] = useState('');
  const [pendingDraft, setPendingDraft] = useState(currentJob?.agent_pending_draft || null);
  const { pending, error, createDraft } = useAgentDraft({ currentJob });

  const visibleMessages = messages.length > 0 ? messages : [WELCOME_MESSAGE];
  const canSend = Boolean(input.trim()) && !pending;
  const selectedPageText = activePage ? `第 ${activePage.page_no} 页 · ${getPageTitle(activePage)}` : '未选择页面';

  const submitMessage = async (messageOverride = '') => {
    const message = String(messageOverride || input).trim();
    if (!message || pending) return;
    const userMessage = {
      id: `local-user-${messages.length}-${message.slice(0, 24)}`,
      role: 'user',
      message,
    };
    setMessages((current) => [...current.filter((item) => item.id !== WELCOME_MESSAGE.id), userMessage]);
    setInput('');

    const response = await createDraft({
      message,
      page_no: activePage?.page_no,
      preview_type: previewType,
      annotations,
      messages: buildClientContext(messages),
    });
    if (!response?.draft) return;

    const serverMessages = normalizeServerMessages(response.messages);
    const fallbackAssistant = {
      id: `local-assistant-${response.draft.draft_id || messages.length}`,
      role: 'assistant',
      message: response.draft.summary,
      draft: response.draft,
    };
    setMessages(serverMessages.length > 0 ? serverMessages : (current) => [...current, fallbackAssistant]);
    setPendingDraft(response.draft);
  };

  const confirmDraft = () => {
    if (!pendingDraft) return;
    onDraftInstructionChange(pendingDraft.instruction || '');
    onDraftConfirmed(pendingDraft);
  };

  return (
    <section className="agent-chat-window" aria-label="Agent 多轮对话">
      <div className="agent-chat-window__head">
        <div>
          <span className="eyebrow">Agent 对话</span>
          <h3>先理解问题，再整理改动</h3>
          <p>{selectedPageText} · 当前看的是 {previewType === 'reference' ? '原稿图' : '元素图'}</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={onOpenImageMarkup} disabled={!activePage}>
          <MousePointer2 size={16} />
          框选标注
        </button>
      </div>

      <div className="quick-actions quick-actions--pending" aria-label="常用反馈">
        {QUICK_PROMPTS.map((prompt) => (
          <button type="button" key={prompt} onClick={() => submitMessage(prompt)} disabled={!activePage || pending}>
            {prompt}
          </button>
        ))}
      </div>

      <div className="chat-thread">
        {visibleMessages.map((message) => (
          <article
            key={message.id}
            className={clsx('chat-bubble', message.role === 'user' ? 'chat-bubble--user' : 'chat-bubble--agent')}
          >
            <span className="chat-bubble__icon">
              {message.role === 'user' ? <UserRound size={15} /> : <Bot size={15} />}
            </span>
            <p>{message.message}</p>
          </article>
        ))}
        {pending && (
          <article className="chat-bubble chat-bubble--agent">
            <span className="chat-bubble__icon"><LoaderCircle className="spin" size={15} /></span>
            <p>我正在把你的描述整理成可执行的编辑草案...</p>
          </article>
        )}
      </div>

      {pendingDraft && (
        <div className="agent-draft-card">
          <div className="agent-draft-card__head">
            <span>待确认改动</span>
            <strong>{pendingDraft.edit_kind === 'text' ? '文字优化' : pendingDraft.edit_kind === 'style' ? '整套风格' : '原稿图/排版'}</strong>
          </div>
          <p>{pendingDraft.summary}</p>
          <ul>
            {(pendingDraft.changes || []).slice(0, 4).map((change) => (
              <li key={change}>{change}</li>
            ))}
          </ul>
          <label>
            可带入编辑页的具体改动
            <textarea
              value={draftInstruction || pendingDraft.instruction || ''}
              onChange={(event) => onDraftInstructionChange(event.target.value)}
              placeholder="确认前也可以手动补充更精确的修改要求"
            />
          </label>
          <button type="button" className="btn btn-primary" onClick={confirmDraft}>
            <CheckCircle2 size={17} />
            同意，进入编辑页
          </button>
        </div>
      )}

      <div className="chat-composer">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="描述原稿图哪里有问题，例如：右侧模块太挤，图标有点像后台系统，整体希望更像咨询汇报..."
        />
        <button type="button" className="btn btn-primary" onClick={() => submitMessage()} disabled={!canSend || !activePage}>
          {pending ? <LoaderCircle className="spin" size={17} /> : <SendHorizontal size={17} />}
          发送给 Agent 理解
        </button>
      </div>

      {error && <div className="form-error">{error}</div>}
      {!activePage && (
        <div className="empty-state">
          先在右侧选择一页原稿图，Agent 才能把“这里”“那块”这类描述落到具体页面。
        </div>
      )}
      <div className="agent-chat-window__hint">
        <MessageSquareText size={15} />
        <span>确认前不会触发生成流水线；确认后会跳到编辑页并填好改动内容。</span>
      </div>
    </section>
  );
};

export default AgentChatPanel;
